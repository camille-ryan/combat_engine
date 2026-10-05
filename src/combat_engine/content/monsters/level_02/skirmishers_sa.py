"""Monster abilities, level 2, skirmishers: the second sweep.

Thirty-eight stat blocks whose rows were still undeclared. `skirmishers.py`
holds the first sweep of this level and this file holds the rest; the split is
by *when* the work was done, not by what the creatures are, so the conventions
that file settled are kept here unchanged, and the shared shapes are imported
from it and from the level 1 sweep rather than copied:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=7)`) and the damage line goes in the header as data
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. Several rows the database
  files as standard actions are plainly traits and are written as such;
* a printed range of "5/10" takes the **normal** range, so the creature shoots
  inside the band where it has no penalty;
* combat advantage is read off the roll (`c.result.advantage`,
  `_had_advantage`) rather than asked of the board afterwards, because
  `resolve.attack` clears `HIDDEN_FROM` the moment the attack is over.

Three things this level made the author stop and think about.

**"Whichever defence is lower" is a defect in the compendium, not a row.**
One attack line here arrives with no defence and no damage at all -- the
extraction lost both -- so that half is named rather than guessed (#360) and
the movement the same row prints is written out in full.

**A target line that narrows by a relation to the attacker has nowhere to
live.** "One creature grabbed by it" and "every creature suffering from this
curse" are both `Target.relation` (#361) -- the hold and the curse are the
attacker's own, which is the asymmetry a plain condition filter cannot carry:
`Target` filters on side, count, size and what is in hand, and on nothing a
creature is undergoing. Where the narrowing is really
about the *caster's* own state -- it must be holding somebody, it must have
cursed somebody -- a `requires=` is declared too, which turns "used and did
nothing" into "correctly not offered".

**Walking through a crowd is `c.overrun`, not `c.move`.** Three rows here
print "it can move through enemies' spaces and attacks each one whose space it
enters". `c.move` refuses an occupied square and reports nothing about what it
passed; `overrun` returns the list, which is the only thing those rows can be
built on.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.skirmishers_sa import (
    _adjacent_foes,
    _armed,
    _beside_kind,
    _bloodied,
    _by_hand,
    _damaged_me,
    _elemental_hurt,
    _foe_moved_within,
    _i_rolled_one,
    _moved_far,
    _vanish_until_it_swings,
    _while_bloodied,
)
from combat_engine.content.monsters.level_02.skirmishers import (
    _advantage_rider,
    _conceal,
    _had_advantage,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
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
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Damage,
    DamageType,
    Effect,
    Ident,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Stats,
    Target,
    Usage,
    When,
    Window,
    World,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Hit,
    Miss,
    RelationCleared,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    distance_between,
    flanked_by,
    has_combat_advantage,
    squares,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_opportunity,
    by_ranged,
    either,
    hits_me,
    targets_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _melee_only(ctx: dict[str, Any]) -> bool:
    """"with melee attacks", asked of the damage context.

    `_by_hand` answers "melee **or** ranged", which several riders here want
    and several others do not; this is the narrower half, and the two cannot
    share a gate without one of them being quietly too generous.
    """
    from combat_engine.engine import get

    row = get(str(ctx.get("power") or ""))
    return row is not None and row.reach.kind == "melee"


def _kin_within(c: Cast, ref: str, radius: int, *, of: int) -> list[int]:
    """Allies off the same stat block, within `radius` of that creature.

    The printed line names the creature's own kind -- "any other <this> within
    5 squares of the target" -- and `Ident.ref` is what says so without a name
    going anywhere near the row.
    """
    out = []
    for mate in c.allies():
        if mate == c.me or distance_between(c.world, mate, of) > radius:
            continue
        ident = c.world.get(mate, Ident)
        if ident is not None and ident.ref == ref:
            out.append(mate)
    return out


def _until_escape(c: Cast, victim: int, held: Effect | None) -> None:
    """End an effect the moment that creature gets out of the grab.

    "Grabbed and taking ongoing 5 damage (**both** until escape)" is two
    effects with one lifetime, and no `When` measures it: a grab ends when the
    relation is cleared, which `RelationCleared` is the only announcement of.
    """
    if held is None:
        return

    def freed(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.target == victim:
            c.world.effects.end(held, "it escaped")

    c.watch(
        RelationCleared, freed, until=When.ENCOUNTER, on=c.me, once=True,
        label=f"{c.ref} hold",
    )


def _aura_holds(c: Cast, ring: int, lay: Any) -> None:
    """Lay something on each enemy inside the aura, and lift it as they leave.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered` and
    `ZoneExited` are exactly the two moments the modifier should arrive and go.
    Whoever is already standing inside is handled at the end -- making the aura
    refreshes membership before its id exists for a listener to recognise.
    """
    held: dict[int, Effect] = {}

    def arrive(who: int) -> None:
        if who in held or who not in c.enemies():
            return
        effect = lay(who)
        if effect is not None:
            held[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            arrive(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(ring):
        arrive(actor)


def _ends_turn_in_aura(c: Cast, radius: int, amount: int) -> None:
    """An aura for the board to draw, and the toll taken as a turn closes.

    Who is inside is asked when the turn ends rather than kept as a list: the
    aura travels with the creature and a stored membership would be stale the
    moment either of them moved.
    """
    me = c.me
    c.aura(radius, until=When.ENCOUNTER)

    def toll(ev: TurnEnd) -> None:
        if ev.actor == me or ev.ghost:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) > radius:
            return
        c.flat(amount, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


def _blinding_cloud(c: Cast, radius: int) -> None:
    """A cloud that blocks sight and blinds whoever is standing in it.

    The blind is held per occupant and lifted on the way out, because "while
    entirely in the cloud" is geometry rather than a duration. The exemption
    the card prints -- everyone *except* this creature is blinded and blinded
    by it -- is the half that cannot be said: `c.zone(blocks_sight=True)` is
    terrain and blinds both sides.
    """
    area = spread({c.here}, radius)
    zone = c.zone(area, blocks_sight=True, until=When.EONT, label=c.ref)
    me = c.me

    def blind(who: int) -> Effect | None:
        return None if who == me else c.blinded(on=who, until=When.ENCOUNTER)

    _aura_holds(c, zone, blind)


def _two_swings(c: Cast, *, then: Any) -> None:
    """Two attacks at one creature, and a rider that wants both to land."""
    landed = 0
    for _ in range(2):
        if c.strike():
            c.hit()
            landed += 1
    if landed == 2:
        then()


def _shift_and_swing(c: Cast, total: int) -> None:
    """Shift, swing once on the way, and spend the rest of the step.

    The distance goes in two halves rather than all at once: "at any point
    during that movement" is what puts a creature in reach that one step to
    one destination would not.
    """
    half = max(1, total // 2)
    c.shift(half)
    foe = next(iter(_adjacent_foes(c, 1)), None)
    if foe is not None:
        c.basic(on=foe)
    rest = total - half
    if rest > 0:
        c.shift(rest)


def _grabbing_something(world: World, eid: int) -> bool:
    """The printed "one creature grabbed by it", asked from the caster's end."""
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def _ridden_by_second_level(world: World, eid: int) -> bool:
    """"While mounted by a friendly rider of 2nd level or higher".

    **`targets`, not `sources`.** The relation is stored
    `set(RIDDEN_BY, mount, rider)`, so a mount's riders are its `targets` and
    its `sources` are whatever *it* is riding -- empty for a mount, every time.
    `c.rider` and `c.mount` are the two directions and read exactly that way.

    This asked `sources`, so the gate was false forever and the two rows that
    require it were never offered -- a Requirement that cannot be met reads as
    a board limitation in `audit.py`, which is why nothing caught it. Found by
    an agent at level 4 hitting the same clause and getting it right.
    """
    for rider in world.relations.targets(Relation.RIDDEN_BY, eid):
        stats = world.get(rider, Stats)
        if stats is not None and stats.level >= 2:
            return True
    return False


def _high_crit(c: Cast, dice: str) -> None:
    """The extra die a "crit: NdN + <max>" line prints.

    Rolled rather than added inside the header: `c.damage` maxes its dice on a
    critical, so an extra die written there would come out at its highest face
    every time. `c.flat(c.roll(...))` is the way to add one.
    """
    if c.crit:
        c.flat(c.roll(dice))


# --------------------------------------------------------------------------
# m1134
# --------------------------------------------------------------------------


@power(
    "m1134a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 3),
)
def m1134a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1134a1",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 3, kind=LIMITED),
)
def m1134a1(c: Cast) -> None:
    """Two swings at one creature; the burn is the price of both landing."""
    _two_swings(c, then=lambda: c.ongoing(5))


@power(
    "m1134a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m1134a2(c: Cast) -> None:
    """A swing and nine points back. The Requirement is a gate rather than a
    body check: a row that looks and returns is an action the policy spent on
    nothing."""
    c.basic()
    c.heal(9, on=c.me)


# --------------------------------------------------------------------------
# m1139
# --------------------------------------------------------------------------


@power(
    "m1139a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 2),
)
def m1139a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1139a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d8", 3, DamageType.PSYCHIC),
)
def m1139a1(c: Cast) -> None:
    """The larger expression replaces the printed one rather than adding to
    it. "At full hit points" is `c.missing` reading zero, which is the only
    question that distinguishes an untouched creature from a nearly untouched
    one."""
    if c.strike():
        if c.missing(on=c.target) == 0:
            c.damage("1d12", 3, dtype=DamageType.PSYCHIC)
        else:
            c.hit()


@power(
    "m1139a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(20),
    target=Target(
        side="any", count=99, everyone=True,
        label="suffering its curse",
        relation=Relation.CURSED_BY,
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 3, DamageType.NECROTIC, kind=LIMITED),
)
def m1139a2(c: Cast) -> None:
    """Everybody carrying the curse, and nobody else.

    The narrowing is the target line now, so the burst is no longer declared
    wide and then talked out of it in the body. Three things went with it: the
    body's `c.cursed` gate, the `requires=` that kept the row from being spent
    on a burst touching nobody, and the marker. An empty pool refuses the row
    on its own, which is what both of the first two were spelling by hand.
    """
    if c.strike():
        c.hit()


@power(
    "m1139a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m1139a3(c: Cast) -> None:
    """The closest enemy, chosen here rather than offered.

    "Closest enemy" is not a target line a player picks from and `Target`
    cannot narrow by distance, so the row takes no target and reads the board.
    One curse at a time is `c.curse`'s own rule.

    The extra damage is armed once however often the minor action is spent: a
    second copy of the rider would pay the 1d6 twice for one printed sentence.
    """
    me, ref = c.me, c.ref
    nearest = min(c.enemies(), key=c.distance, default=None)
    if nearest is None:
        return
    c.curse(on=nearest)

    if not _armed(c, ref):

        def rider(ev: Hit) -> None:
            if ev.attacker == me and c.cursed(on=ev.target):
                c.damage("1d6", on=ev.target, detail=ref)

        c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


_M1139_ATTACKED = "an enemy makes a melee or ranged attack against it"


@power(
    "m1139a4",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    trigger=_M1139_ATTACKED,
    on=Trigger(
        AttackDeclared,
        both(targets_me, either(by_melee, by_ranged)),
        _M1139_ATTACKED,
    ),
    dropped=("query.kills_by(world, eid)",),
)
def m1139a4(c: Cast) -> None:
    """A charge that grows on kills and is spent in one discharge.

    The tally is kept as a `When.ENCOUNTER` modifier and read back with
    `c.total`, so there is no state in this module and nothing to reset
    between fights. What is dropped is *when the counting starts*: a row with
    a declared trigger only runs its body when the trigger fires, so the
    kill-watch is armed the first time an enemy swings at the creature and
    anything killed before that is not counted anywhere to be read back.

    The half-damage branch answers `DamageRolled` rather than the declared
    `AttackDeclared`, because at declaration time there is no amount to halve
    -- and it is laid `once`, so it spends itself on the triggering blow.
    """
    me, ref = c.me, c.ref
    key, label = f"{ref} points", f"{ref} kills"

    if not _armed(c, label):

        def counted(ev: Dropped) -> None:
            if team(c.world, ev.actor) is not team(c.world, me) and c.cursed(on=ev.actor):
                c.bonus(key, 1, on=me, until=When.ENCOUNTER)

        c.watch(Dropped, counted, until=When.ENCOUNTER, on=me, label=label)

    points = c.total(key, on=me)
    if points <= 0:
        return

    foe = getattr(c.trigger, "attacker", None)
    dealt = c.damage(
        f"{points}d6",
        dtypes=(DamageType.NECROTIC, DamageType.PSYCHIC),
        on=foe,
        detail=ref,
    )
    _reset_tally(c, key)
    if dealt >= 12:
        c.bonus(key, 1, on=me, until=When.ENCOUNTER)

        def halve(ev: DamageRolled) -> None:
            if getattr(ev, "target", None) == me:
                ev.amount -= ev.amount // 2

        c.watch(
            DamageRolled, halve, until=When.EOT, window=Window.BEFORE, on=me,
            once=True, label=f"{ref} softened",
        )


def _reset_tally(c: Cast, key: str) -> None:
    """Take the counter back to nothing by ending every point standing on it.

    Matched on the modifier rather than on the effect's label: `c.bonus`
    stamps the row's ref, and this row lays more than one sort.
    """
    for effect in list(c.world.effects.of(c.me)):
        if any(mod.what == key for _owner, mod in effect.mods):
            c.world.effects.end(effect, "the aura discharged")


@power(
    "m1139a5",
    level=2,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1139a5(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(on=c.me, until=When.SONT)


# --------------------------------------------------------------------------
# m115691
# --------------------------------------------------------------------------


def _ran_and_swung(c: Cast, far: int, dice: str) -> None:
    """Extra damage on melee attacks for ending a move a long way off.

    The window is "until the start of its next turn", which is measured
    against the creature carrying it, so `When.SONT` says it exactly.
    """
    me = c.me

    def pay() -> None:
        c.bonus(
            "damage", 0, dice=dice, on=me, until=When.SONT, when=_melee_only,
        )

    _moved_far(c, me, far, pay)


@power(
    "m115691a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115691a0(c: Cast) -> None:
    """A trait, whatever the database files it as: nothing is spent on it and
    it arms the two watches that hold it for the fight."""
    _ran_and_swung(c, 4, "1d6")


@power(
    "m115691a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 4),
)
def m115691a1(c: Cast) -> None:
    """"+7, or +8 while bloodied" is one printed total and one gated point on
    top of it, taken at the roll rather than laid as a standing modifier: two
    untyped bonuses of the same kind do not add, and a modifier would have to
    be lifted again the moment the creature was healed."""
    if c.strike(plus=1 if c.bloodied(on=c.me) else 0):
        c.hit()
    c.shift(2)


@power(
    "m115691a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d10", 4, kind=LIMITED, half_on_miss=True),
)
def m115691a2(c: Cast) -> None:
    """The grant is unqualified, so it is `to="team"`: the creature and every
    ally, not the caster alone."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SAVE_ENDS, to="team")
    else:
        c.hit(half=True)


@power(
    "m115691a3",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d6", 2, DamageType.LIGHTNING, kind=LIMITED),
)
def m115691a3(c: Cast) -> None:
    if c.strike():
        c.hit()


_M115691_BLOODIED = "it is bloodied"


@power(
    "m115691a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M115691_BLOODIED,
    on=Trigger(Bloodied, about_me, _M115691_BLOODIED),
)
def m115691a4(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m115801
# --------------------------------------------------------------------------


@power(
    "m115801a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115801a0(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m115801a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m115801a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m115801a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 5),
)
def m115801a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m115801a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m115801a3(c: Cast) -> None:
    """"Recharge when the attack misses" on top of the die the block records.

    `c.restore_use` hands the use straight back, which is what the printed
    sentence does; the 6+ the database carries stays declared because that is
    what the card prints and what `cards.py` compares against.
    """
    if c.strike():
        c.hit()
        c.dazed()
    else:
        c.restore_use(c.ref)
    c.shift(1)


# --------------------------------------------------------------------------
# m1484
# --------------------------------------------------------------------------


@power(
    "m1484a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d8", 4),
    dropped=("c.cannot_attack(when=)",),
)
def m1484a0(c: Cast) -> None:
    """It fastens on and feeds, and the burn lasts exactly as long as the hold.

    The defences it gains are gated on the hold rather than laid flat, so they
    come off the moment the creature it is attached to gets free. What is
    dropped is the other half of being attached: it makes no attack rolls
    while it holds somebody, and `c.cannot_attack` takes no gate, so writing
    it bare would silence the creature for the rest of the fight.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    c.grab()
    _until_escape(c, victim, c.ongoing(5, until=When.ENCOUNTER))
    if not _armed(c, c.ref):
        attached = lambda ctx: bool(c.grabbing())  # noqa: E731
        for defence in (AC, REF):
            c.bonus(
                defence, 5, on=c.me, until=When.ENCOUNTER, when=attached,
            )
        c.effect(c.ref, on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m1488
# --------------------------------------------------------------------------


@power(
    "m1488a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 4),
)
def m1488a0(c: Cast) -> None:
    if c.strike(plus=1 if c.bloodied(on=c.me) else 0):
        c.hit()


@power(
    "m1488a1",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 4, kind=LIMITED),
)
def m1488a1(c: Cast) -> None:
    if c.strike(plus=1 if c.bloodied(on=c.me) else 0):
        c.hit()
        c.grants_advantage(until=When.EONT)


@power(
    "m1488a2",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d6", 2, DamageType.LIGHTNING, kind=LIMITED),
)
def m1488a2(c: Cast) -> None:
    if c.strike(plus=1 if c.bloodied(on=c.me) else 0):
        c.hit()


@power(
    "m1488a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1488a3(c: Cast) -> None:
    """A racial bonus, gated rather than laid and lifted.

    `kind="racial"` is the word the card prints in front of "bonus" and the
    gate is read at each roll, so the point comes and goes with the wound
    without anything having to watch for it.
    """
    me = c.me
    c.bonus(
        "attack", 1, on=me, kind="racial", until=When.ENCOUNTER,
        when=lambda ctx: _bloodied(c.world, me),
    )


@power(
    "m1488a4",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1488a4(c: Cast) -> None:
    _ran_and_swung(c, 4, "1d6")


_M1488_BLOODIED = "it is bloodied"


@power(
    "m1488a5",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1488_BLOODIED,
    on=Trigger(Bloodied, about_me, _M1488_BLOODIED),
)
def m1488a5(c: Cast) -> None:
    """"When first bloodied" needs no guard: `Bloodied` is announced once."""
    c.shift(3)


# --------------------------------------------------------------------------
# m1508
# --------------------------------------------------------------------------


@power(
    "m1508a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 1),
)
def m1508a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m1508a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 3),
)
def m1508a1(c: Cast) -> None:
    """"5/10" takes the normal range: the band beyond it costs the creature
    two to hit, which is a penalty and not a reach."""
    if c.strike():
        c.hit()


@power(
    "m1508a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d8", 1, kind=LIMITED),
)
def m1508a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()
    c.shift(1)


@power(
    "m1508a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1508a3(c: Cast) -> None:
    """The printed line names melee and ranged attacks, so a close blast's
    blow is left out -- which is what `reaches` is for."""
    _advantage_rider(c, "1d6", ("melee", "ranged"))


# --------------------------------------------------------------------------
# m1523
# --------------------------------------------------------------------------


@power(
    "m1523a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m1523a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1523a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m1523a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1523a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m1523a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


_M1523_MOVED = "an enemy within 5 squares moves"


@power(
    "m1523a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(5),
    target=NO_TARGET,
    trigger=_M1523_MOVED,
    on=Trigger(AttackDeclared, _foe_moved_within(5), _M1523_MOVED),
    todo=("c.spring_trap()",),
)
def m1523a3(c: Cast) -> None:
    """The whole of this row is setting off a trap on purpose.

    A trap is an entity that attacks like anything else, and `c.is_trap` can
    find one, but nothing can make one go off: there is no verb for "resolve
    that trap's attack now" and the attack belongs to the trap rather than to
    this creature, so `c.use_power` cannot borrow it either. Named rather than
    approximated -- rolling the trap's attack from here would make this
    creature the attacker, which is the one thing the printed line is not.
    """


@power(
    "m1523a4",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1523a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m1523a5",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1523a5(c: Cast) -> None:
    """"All defences" is four bonuses, said once each.

    The gate reads the attacker off the attack context, which is where
    `c.is_trap` is meant to be asked from: a trap has no `Health` and is on
    the board like anything else, so the question is about who swung and not
    about the row that swung.
    """
    sprung = lambda ctx: c.is_trap(ctx.get("attacker"))  # noqa: E731
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 6, on=c.me, until=When.ENCOUNTER, when=sprung)


# --------------------------------------------------------------------------
# m1957
# --------------------------------------------------------------------------


@power(
    "m1957a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d4", 2, DamageType.NECROTIC),
)
def m1957a0(c: Cast) -> None:
    """The burn is untyped where the blow is necrotic: the card says "ongoing
    5 damage" with no word in front of it, and a type the page does not print
    would make the row stack differently against anything resistant."""
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m1957a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1957a1(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and _had_advantage(ev):
            c.prone(on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# --------------------------------------------------------------------------
# m3211
# --------------------------------------------------------------------------


@power(
    "m3211a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m3211a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m3211a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m3211a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()
    c.shift(1)


@power(
    "m3211a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m3211a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m3211a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3211a3(c: Cast) -> None:
    _advantage_rider(c, "1d6")


# --------------------------------------------------------------------------
# m3230
# --------------------------------------------------------------------------


@power(
    "m3230a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m3230a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3230a1",
    level=2,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    requires=_ridden_by_second_level,
    requires_text="it must be carrying a rider of 2nd level or higher",
)
def m3230a1(c: Cast) -> None:
    """The rider's level is read off `Stats`, which is where a creature's
    level lives -- `Ident` carries the ref and the role and no number."""
    c.shift(4)


@power(
    "m3230a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.grant_action('mount')",),
)
def m3230a2(c: Cast) -> None:
    """The whole of this line is "a creature of that size may ride it".

    `c.ride` can establish the relation but nothing offers mounting as an
    action, so there is no moment at which this row can become true. Setting
    the relation from here would put a rider on it that nobody chose.
    """


# --------------------------------------------------------------------------
# m3233
# --------------------------------------------------------------------------


@power(
    "m3233a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 6),
)
def m3233a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3233a1",
    level=2,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m3233a1(c: Cast) -> None:
    c.shift(2)


@power(
    "m3233a2",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_ridden_by_second_level,
    requires_text="it must be carrying a rider of 2nd level or higher",
)
def m3233a2(c: Cast) -> None:
    c.bonus("speed", 4, on=c.me, until=When.EONT)


# --------------------------------------------------------------------------
# m3325
# --------------------------------------------------------------------------


@power(
    "m3325a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d10", 1),
)
def m3325a0(c: Cast) -> None:
    """"One of its allies" is one creature, so the step is given to the first
    one in reach rather than to the whole side."""
    if not c.strike():
        return
    c.hit()
    mate = next(
        (a for a in c.allies() if a != c.me and distance_between(c.world, c.me, a) <= 5),
        None,
    )
    if mate is not None:
        c.shift(1, who=mate)


@power(
    "m3325a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 1),
)
def m3325a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3325a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3325a2(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee", "ranged"))


_M3325_DOWN = "it drops to 0 hit points"


@power(
    "m3325a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3325_DOWN,
    on=Trigger(Dropped, about_me, _M3325_DOWN),
)
def m3325a3(c: Cast) -> None:
    """One last swing. `about_me` is right here because `Dropped` names its
    subject `actor`, which is the only field that predicate reads."""
    foe = next(iter(_adjacent_foes(c, 1)), None)
    if foe is not None:
        c.basic(on=foe)


# --------------------------------------------------------------------------
# m3329
# --------------------------------------------------------------------------


@power(
    "m3329a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d8", 1),
)
def m3329a0(c: Cast) -> None:
    """"(crit 9 + 1d8)" is the maximum of the printed line plus one more die:
    nine is 1d8 maxed and the flat 1 on top of it, so the extra 1d8 is the
    only part that is not already what a critical does."""
    if c.strike():
        c.hit()
        _high_crit(c, "1d8")
    c.shift(1)


@power(
    "m3329a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3329a1(c: Cast) -> None:
    """`charge` is a plain attribute on the `Hit` rather than a declared
    field, so it is read with `getattr`."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not getattr(ev, "charge", False):
            return
        c.damage("1d8", on=ev.target, detail=c.ref)
        c.prone(on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3329a2",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m3329a2(c: Cast) -> None:
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER)
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER)
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m3520
# --------------------------------------------------------------------------


@power(
    "m3520a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m3520a0(c: Cast) -> None:
    """Two expressions, one of them typed: the header carries the printed Hit
    line and the fire is added beside it, because a single `Damage` cannot be
    half untyped and half fire."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.FIRE)


@power(
    "m3520a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    dropped=("etl.monster.attack_defence()",),
)
def m3520a1(c: Cast) -> None:
    """The run plays; the attack line the card also prints cannot be declared.

    That line reads "+5 vs <one> or <other> (whichever is lower)" with both
    defence names and the whole damage expression gone -- a defect in the
    extraction (#360), not a row. Picking a defence would be an invented
    number in a header the policy reads as printed, so it is named instead and
    the slam is borrowed from the at-will, which is the attack the printed
    sentence actually says it makes.

    The toll on anybody who swings at it during the run is a watch that lives
    for the turn and no longer: "during this movement" is the window, and a
    `When.EOT` effect expires with the turn it was laid in.
    """
    me = c.me

    def scald(ev: AttackDeclared) -> None:
        foe = getattr(ev, "attacker", None)
        if foe is not None and foe != me:
            c.flat(5, dtype=DamageType.FIRE, on=foe)

    watch = c.watch(
        AttackDeclared, scald, until=When.EOT, on=me, label=f"{c.ref} wake",
    )
    struck: set[int] = set()
    for foe in c.overrun():
        if foe not in struck:
            struck.add(foe)
            c.use_power("m3520a0", on=foe, spend=False)
    c.world.effects.end(watch, "the run ended")


# --------------------------------------------------------------------------
# m3538
# --------------------------------------------------------------------------


@power(
    "m3538a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m3538a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    mate = next(
        (a for a in c.allies() if a != c.me and distance_between(c.world, c.me, a) <= 5),
        None,
    )
    if mate is not None:
        c.shift(1, who=mate)


@power(
    "m3538a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m3538a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3538a2",
    level=2,
    usage=ENCOUNTER,
    uses=3,
    action=STANDARD,
    reach=AreaBurst(1, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d6", 0, DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m3538a2(c: Cast) -> None:
    """"Usable three times only" is `uses=3` and not a usage: `usage` can say
    once a fight or every round and has no word for a budget."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m3538a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3538a3(c: Cast) -> None:
    _advantage_rider(c, "1d6")


_M3538_DOWN = "it drops to 0 hit points"


@power(
    "m3538a4",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3538_DOWN,
    on=Trigger(Dropped, about_me, _M3538_DOWN),
)
def m3538a4(c: Cast) -> None:
    c.basic()


# --------------------------------------------------------------------------
# m4495
# --------------------------------------------------------------------------


@power(
    "m4495a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m4495a0(c: Cast) -> None:
    if c.strike(plus=1 if c.bloodied(on=c.me) else 0):
        c.hit()


@power(
    "m4495a1",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m4495a1(c: Cast) -> None:
    """Swing, then go round behind. `share=True` is what lets the step land in
    the creature's own square on the way past -- `movement.shift` refuses an
    occupied square outright, so without it "can shift through the target's
    square" changes nothing at all.
    """
    foe = c.target
    c.use_power("m4495a0", on=foe)
    for sq in sorted(spread(set(squares(c.world, foe)), 1)):
        if c.shift(3, to=sq, share=True):
            return
    c.shift(3, share=True)


@power(
    "m4495a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d8", 4, DamageType.FIRE),
)
def m4495a2(c: Cast) -> None:
    if c.strike(plus=1 if c.bloodied(on=c.me) else 0):
        c.hit()


_M4495_HIT = "it is hit by a melee or ranged attack"


@power(
    "m4495a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4495_HIT,
    on=Trigger(Hit, both(hits_me, either(by_melee, by_ranged)), _M4495_HIT),
)
def m4495a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m4495a4",
    level=2,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4495a4(c: Cast) -> None:
    c.shift(6)


# --------------------------------------------------------------------------
# m4617
# --------------------------------------------------------------------------


@power(
    "m4617a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.shift(swap=)",),
)
def m4617a0(c: Cast) -> None:
    """The whole of this row is a narrowing of what a shift may end on.

    `c.swap` trades two creatures' squares and `c.shift(share=True)` lets a
    step pass through an occupied one, but neither is this: the printed line
    changes the *destination rule* for every shift the creature makes, and
    there is nothing to hang that on. Doing it from here -- swapping on the
    spot -- would be a move nobody chose, at a moment nothing is shifting.
    """


@power(
    "m4617a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m4617a1(c: Cast) -> None:
    """The bigger expression replaces the printed one; `c.result.advantage` is
    read off the roll because the board has already forgotten."""
    if c.strike():
        if c.result is not None and c.result.advantage:
            c.damage("2d6", 3)
        else:
            c.hit()


@power(
    "m4617a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    dropped=("c.retarget_defence()",),
)
def m4617a2(c: Cast) -> None:
    """The swing lands; the choice of defence is the half that cannot be said.

    `c.use_power` runs the other row at this row's cost and leaves its result
    in `c.result`, so "recharge if the attack misses" is answerable. Sending
    that attack at Fortitude or Reflex instead of AC is a different operation
    -- the defence is in the borrowed row's header, which is data -- and
    nothing redirects it.
    """
    c.use_power("m4617a1")
    if not c.landed:
        c.restore_use(c.ref)


_M4617_MISSED = "it is missed by an attack"


@power(
    "m4617a3",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4617_MISSED,
    on=Trigger(Miss, targets_me, _M4617_MISSED),
)
def m4617a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4679
# --------------------------------------------------------------------------


@power(
    "m4679a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 4),
)
def m4679a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4679a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d4", 4),
)
def m4679a1(c: Cast) -> None:
    """A swarm walking over a line and biting everything on the way.

    `c.overrun` rather than `c.move`: a move refuses an occupied square and
    reports nothing about what it passed, so "once against each enemy whose
    square it enters" has nothing to iterate. The set keeps it to once each,
    which is the word the card prints.
    """
    struck: set[int] = set()
    for foe in c.overrun():
        if foe in struck:
            continue
        struck.add(foe)
        if c.strike(on=foe):
            c.hit(on=foe)


@power(
    "m4679a2",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4679a2(c: Cast) -> None:
    """The same walk with nothing on the end of it."""
    c.overrun()


# --------------------------------------------------------------------------
# m4683
# --------------------------------------------------------------------------


@power(
    "m4683a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d12", 3),
)
def m4683a0(c: Cast) -> None:
    """"crit: 1d12 + 15" is fifteen -- a maxed 1d12 and the flat 3 -- with one
    more 1d12 beside it, which is the high crit the weapon carries."""
    if c.strike():
        c.hit()
        _high_crit(c, "1d12")


@power(
    "m4683a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d12", 3),
)
def m4683a1(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        c.hit()
        _high_crit(c, "1d12")
    c.shift(1)


@power(
    "m4683a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d12", 2, kind=LIMITED),
    charges=True,
)
def m4683a2(c: Cast) -> None:
    """A leap into reach, declared as a charge so the engine measures the way
    a charge needs: without `charges=True` the row is refused whenever the
    victim is further off than a sword, which is every situation it is for.

    "Recharge when first bloodied" on top of the die the block records, so the
    use comes back the moment the dwarf is hurt as well as on a 6.
    """
    me = c.me
    c.no_provoke(on=me, until=When.EOT)
    c.jump(c.speed_of(me), on=me)
    if c.strike():
        c.hit()
    if not _armed(c, f"{c.ref} wind"):

        def hurt(ev: Bloodied) -> None:
            if ev.actor == me:
                c.restore_use(c.ref)

        c.watch(
            Bloodied, hurt, until=When.ENCOUNTER, on=me, once=True,
            label=f"{c.ref} wind",
        )


@power(
    "m4683a3",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4683a3(c: Cast) -> None:
    """"Each dwarf ally" is a kind rather than a stat block, so `c.is_kind`
    answers it and no ref has to be named."""
    for mate in c.allies():
        if mate == c.me or distance_between(c.world, c.me, mate) > 5:
            continue
        if c.is_kind("dwarf", on=mate):
            c.shift(2, who=mate)


# --------------------------------------------------------------------------
# m4691
# --------------------------------------------------------------------------


def _bigger_with_advantage(c: Cast, dice: str, plain: int, better: int) -> None:
    """"2d4+4, or 2d4+8 with combat advantage" -- one expression or the other."""
    if c.result is not None and c.result.advantage:
        c.damage(dice, better)
    else:
        c.damage(dice, plain)


@power(
    "m4691a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 4),
)
def m4691a0(c: Cast) -> None:
    if c.strike():
        _bigger_with_advantage(c, "2d4", 4, 8)
        c.slide(1)


@power(
    "m4691a1",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 4, kind=LIMITED),
)
def m4691a1(c: Cast) -> None:
    if c.strike():
        _bigger_with_advantage(c, "2d4", 4, 8)
        c.blinded()


_M4691_HURT = "it takes damage"


@power(
    "m4691a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M4691_HURT,
    on=Trigger(DamageApplied, _damaged_me, _M4691_HURT),
)
def m4691a2(c: Cast) -> None:
    """"Until it attacks or until the end of its next turn" is two endings,
    and the second is the one a `When` can say; the first is a watch on the
    creature's own `Hit` and `Miss`."""
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m4691a3",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4691a3(c: Cast) -> None:
    c.jump(7, on=c.me)


@power(
    "m4691a4",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:stealth",),
)
def m4691a4(c: Cast) -> None:
    """Out of sight before the fight starts, wherever the ground allows it.

    The printed line lowers what hiding *requires* -- any cover or any
    concealment rather than superior cover -- at one moment, the initiative
    check. There is no requirement in the engine to lower and no stealth check
    rolled on a board, so the narrowing has no combat meaning and what is left
    that can be said is the consequence: as the fight opens it is unseen by
    everybody whose line to it is blocked. A trait rather than a repeated
    action, because the printed moment happens once.
    """
    _conceal(c)


# --------------------------------------------------------------------------
# m4693
# --------------------------------------------------------------------------


@power(
    "m4693a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 2),
)
def m4693a0(c: Cast) -> None:
    if c.strike():
        _bigger_with_advantage(c, "1d4", 2, 6)
        c.ongoing(5, DamageType.POISON)


@power(
    "m4693a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 2),
)
def m4693a1(c: Cast) -> None:
    if c.strike():
        _bigger_with_advantage(c, "1d4", 2, 6)
        c.ongoing(5, DamageType.POISON)


@power(
    "m4693a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4693a2(c: Cast) -> None:
    """"At any point during that movement" is why the shift is spent in two
    halves: one step to one destination puts nobody in reach who was not
    already there."""
    _shift_and_swing(c, 3)


# --------------------------------------------------------------------------
# m5115
# --------------------------------------------------------------------------


@power(
    "m5115a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m5115a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5115a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m5115a1(c: Cast) -> None:
    """The pack closes in. "Toward the target" is the step's direction, which
    `to=` says by naming a square beside the victim."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    for mate in _kin_within(c, "m5115", 5, of=victim):
        for sq in sorted(spread(set(squares(c.world, victim)), 1)):
            if c.shift(2, who=mate, to=sq):
                break


@power(
    "m5115a2",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5115a2(c: Cast) -> None:
    c.shift(3)


_M5115_DOWN = "it drops to 0 hit points"


@power(
    "m5115a3",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(3),
    target=NO_TARGET,
    trigger=_M5115_DOWN,
    on=Trigger(Dropped, about_me, _M5115_DOWN),
)
def m5115a3(c: Cast) -> None:
    """A death that buys the pack a round of free bites.

    `team()` is compared directly rather than asking `c.allies()`:
    `query.allies` filters out the dead and the creature this answers for has
    just dropped, so its own membership test would be false every time.
    """
    me = c.me
    mine = team(c.world, me)
    for other in c.world.entities:
        if other == me or team(c.world, other) is not mine:
            continue
        if distance_between(c.world, me, other) > 3:
            continue
        ident = c.world.get(other, Ident)
        if ident is not None and ident.ref == "m5115":
            c.basic(who=other)


_M5115_BURNED = "it takes acid, cold, fire, lightning or thunder damage"


@power(
    "m5115a4",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5115_BURNED,
    on=Trigger(DamageApplied, _elemental_hurt, _M5115_BURNED),
)
def m5115a4(c: Cast) -> None:
    """The resistance is to whatever came in, so the type is read off the
    triggering event rather than chosen in the header."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m5310
# --------------------------------------------------------------------------


@power(
    "m5310a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignores_difficult(when=)",),
)
def m5310a0(c: Cast) -> None:
    """The whole of this row is the narrowing: it ignores rough ground *when
    it shifts* and not when it walks. `c.ignores_difficult` writes a terrain
    word and takes no gate, so installing it bare would be a row stronger
    than its card."""


@power(
    "m5310a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m5310a1(c: Cast) -> None:
    """The step is ranked `toward=` the creature just hit. The card gives it no
    direction, and m5310a3 is two uses of this row at one creature -- so this
    step lands between those two swings, and unranked it put the second out of
    reach. Ranking only: `World.decide` still sees every square."""
    if c.strike():
        c.hit()
        c.shift(1, toward=c.target)


@power(
    "m5310a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 3),
)
def m5310a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5310a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m5310a3(c: Cast) -> None:
    """Two uses of the row that prints the blade, not two basic attacks: the
    shift on each of them is part of that row and comes along."""
    victim = c.target
    landed = 0
    for _ in range(2):
        c.use_power("m5310a1", on=victim, spend=False)
        landed += 1 if c.landed else 0
    if landed == 2:
        c.ongoing(5, on=victim)


@power(
    "m5310a4",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.WEAPON],
    todo=("c.counts_as(property=)",),
)
def m5310a4(c: Cast) -> None:
    """The whole of this row is lending one weapon property to one other row.

    `_high_crit` reads `"high crit" in weapon.properties`, so the mechanism
    exists -- what is missing is any way to put the word there for a while.
    `c.maximise` is the nearest verb and is a different thing: it maxes the
    dice rather than adding the extra one a high crit pays out.
    """


@power(
    "m5310a5",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll",
    on=Trigger(AttackRolled, _i_rolled_one, "it makes an attack roll"),
)
def m5310a5(c: Cast) -> None:
    """The second result stands, good or bad. Answered on `AttackRolled`,
    which is emitted before the hit or the miss, so the new number is the one
    the attack resolves on."""
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m5365
# --------------------------------------------------------------------------


@power(
    "m5365a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignores_difficult(when=)",),
)
def m5365a0(c: Cast) -> None:
    """Rough ground is ignored *when it shifts* and not when it walks, and
    `c.ignores_difficult` takes a terrain word and no gate."""


@power(
    "m5365a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m5365a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5365a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5365a2(c: Cast) -> None:
    """Swing, slide round, and swing again at whoever that flanked.

    The step is aimed at a square that flanks somebody rather than taken
    blind: `query.flanked_by` asks the board the question the printed line
    asks, and it can only be true of a destination that was chosen for it.
    """
    first = c.target
    c.use_power("m5365a1", on=first, spend=False)
    half = max(1, c.speed_of(c.me) // 2)
    for foe in c.enemies():
        if foe == first:
            continue
        for sq in sorted(spread(set(squares(c.world, foe)), 1)):
            if not c.shift(half, to=sq):
                continue
            if flanked_by(c.world, foe, c.me):
                c.use_power("m5365a1", on=foe, spend=False)
            return
    c.shift(half)


@power(
    "m5365a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m5365a3(c: Cast) -> None:
    """One ally, and which verb it gets depends on what it is: its own kind
    shifts where anybody else walks."""
    mate = next(
        (
            a
            for a in c.allies()
            if a != c.me and distance_between(c.world, c.me, a) <= 20
        ),
        None,
    )
    if mate is None:
        return
    half = max(1, c.speed_of(mate) // 2)
    ident = c.world.get(mate, Ident)
    if ident is not None and ident.ref == "m5365":
        c.shift(half, who=mate)
    else:
        c.move(half, who=mate)


@power(
    "m5365a4",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll",
    on=Trigger(AttackRolled, _i_rolled_one, "it makes an attack roll"),
)
def m5365a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m5393
# --------------------------------------------------------------------------


@power(
    "m5393a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5393a0(c: Cast) -> None:
    """`opportunity` is a key the attack context carries, so the narrowing is
    a gate on the bonus rather than something that has to be watched for."""
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m5393a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 1),
)
def m5393a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.POISON)


@power(
    "m5393a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6, kind=LIMITED),
    narrative=("skill:stealth",),
)
def m5393a2(c: Cast) -> None:
    """Strike, withdraw, and vanish wherever the ground allows it.

    The stealth check is the narrative clause: no check is rolled on a board
    and there is no hiding requirement to lower, so what is written is the
    consequence the printed line is after -- unseen by everybody whose line to
    it the retreat has broken.
    """
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
    c.shift(5)
    _conceal(c)


# --------------------------------------------------------------------------
# m5753
# --------------------------------------------------------------------------


@power(
    "m5753a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5753a0(c: Cast) -> None:
    """Both bonuses are gated rather than laid and lifted: the pack shuffles
    every round and a watch on every step would be answering the same question
    the gate answers at the roll."""
    beside = _beside_kind("m5753")
    me = c.me
    together = lambda ctx: beside(c.world, me)  # noqa: E731
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=together)
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=together)


@power(
    "m5753a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 5),
)
def m5753a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    for mate in _kin_within(c, "m5753", 2, of=c.me):
        if c.shift(2, who=mate):
            break


_M5753_CAUGHT = "it is hit by an opportunity attack"


@power(
    "m5753a2",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5753_CAUGHT,
    on=Trigger(Hit, both(hits_me, by_opportunity), _M5753_CAUGHT),
)
def m5753a2(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m6027
# --------------------------------------------------------------------------


@power(
    "m6027a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6027a0(c: Cast) -> None:
    """Hard to see for having covered ground, measured against where the turn
    began -- which is only knowable at the start of that turn, so the square
    is recorded then and read back as the turn closes."""
    me = c.me
    _moved_far(c, me, 3, lambda: c.conceal(on=me, until=When.SONT))


@power(
    "m6027a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m6027a1(c: Cast) -> None:
    if c.strike():
        if c.result is not None and c.result.advantage:
            c.damage("2d6", 4)
        else:
            c.hit()


@power(
    "m6027a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m6027a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6027a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    once_per_round=True,
    attack=Attack(vs=REF, printed=5),
)
def m6027a3(c: Cast) -> None:
    """No damage at all: the grant is the whole of the hit line, and it runs
    out at the end of this turn rather than the next one."""
    if c.strike():
        c.grants_advantage(until=When.EOT)


# --------------------------------------------------------------------------
# m6396
# --------------------------------------------------------------------------


def _poison_if_exposed(c: Cast, amount: int) -> None:
    """"If the target is granting combat advantage to it, ongoing N poison."

    Read off the roll: `resolve.attack` clears `HIDDEN_FROM` the moment the
    attack is over, so asking the board again answers about a world that no
    longer exists.
    """
    if c.result is not None and c.result.advantage:
        c.ongoing(amount, DamageType.POISON)


@power(
    "m6396a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m6396a0(c: Cast) -> None:
    """The step is ranked `toward=` its own target. The card gives it no
    direction, and m6396a2 is this row followed by m6396a1 at the same
    creature -- so this step lands between the two swings, and unranked it put
    the second out of reach. Ranking only: `World.decide` still sees every
    square."""
    if c.strike():
        c.hit()
        _poison_if_exposed(c, 3)
    c.shift(1, toward=c.target)


@power(
    "m6396a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m6396a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        _poison_if_exposed(c, 3)
    c.shift(2)


@power(
    "m6396a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m6396a2(c: Cast) -> None:
    """Both blades at one creature, as two uses of the rows that print them --
    each brings its own shift, which is why this is not two basic attacks."""
    victim = c.target
    c.use_power("m6396a0", on=victim, spend=False)
    c.use_power("m6396a1", on=victim, spend=False)
    if not _armed(c, f"{c.ref} wind"):
        me = c.me

        def hurt(ev: Bloodied) -> None:
            if ev.actor == me:
                c.restore_use(c.ref)

        c.watch(
            Bloodied, hurt, until=When.ENCOUNTER, on=me, once=True,
            label=f"{c.ref} wind",
        )


@power(
    "m6396a3",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m6396a3(c: Cast) -> None:
    """A cloud that blinds whoever is inside it.

    What is dropped is the exemption the card prints: the zone blocks line of
    sight for every creature **except this one**, and `c.zone(blocks_sight=)`
    is terrain that blinds both sides with nothing to carve out. The blind the
    occupants take is written per creature and lifted as they leave, which is
    what "while entirely in the cloud" means.
    """
    _blinding_cloud(c, 1)


# --------------------------------------------------------------------------
# m6511
# --------------------------------------------------------------------------


@power(
    "m6511a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 5),
)
def m6511a0(c: Cast) -> None:
    """The step is an Effect line and is taken whether or not the bite lands.
    "If grabbing no target" is asked of the board, which is where a grab
    lives."""
    c.shift(1)
    if c.strike():
        c.hit()
        if not c.grabbing():
            c.grab()


@power(
    "m6511a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d10", 4, kind=LIMITED),
    dropped=("c.restrict_action()",),
)
def m6511a1(c: Cast) -> None:
    """"The target cannot use the escape action" is the one absence: actions
    can be *granted* (`c.grant_action` knows the word) and nothing takes one
    away, so the hold is not actually harder to get out of.
    """
    if c.strike():
        c.hit()


@power(
    "m6511a2",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6511a2(c: Cast) -> None:
    """It drags what it is holding along behind it, which is a pull of the
    same distance rather than anything the victim chooses."""
    held = list(c.grabbing())
    far = c.speed_of(c.me)
    if c.shift(far):
        for victim in held:
            c.pull(far, on=victim)


# --------------------------------------------------------------------------
# m6566
# --------------------------------------------------------------------------


@power(
    "m6566a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 4),
)
def m6566a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(2)


# --------------------------------------------------------------------------
# m6568
# --------------------------------------------------------------------------


@power(
    "m6568a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6568a0(c: Cast) -> None:
    """An aura 1 that makes it harder to swing or shoot from inside the cloud.

    The penalty is held per occupant and comes off on the way out, because the
    printed line is about standing there rather than about a duration. It is
    narrowed to melee and ranged attacks, so a close burst thrown from inside
    is unaffected -- which is what `_by_hand` reads off the power.
    """
    ring = c.aura(1, until=When.ENCOUNTER)

    def hamper(who: int) -> Effect | None:
        return c.penalty(
            "attack", 2, on=who, until=When.ENCOUNTER,
            when=lambda ctx: _by_hand(str(ctx.get("power") or "")),
        )

    _aura_holds(c, ring, hamper)


@power(
    "m6568a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6568a1(c: Cast) -> None:
    """Only while it is flying, which `c.moving_as` answers: `Movement.modes`
    says what a creature *can* do and this is about what it is doing now."""
    me = c.me
    c.no_provoke(
        on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.moving_as("fly", on=me),
    )


@power(
    "m6568a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:acrobatics",),
)
def m6568a2(c: Cast) -> None:
    """What a swarm is: a space anybody may walk into, and nothing to shove.

    "It can squeeze through any opening large enough for one of the creatures
    it comprises" is the narrative clause, and squeezing through a gap is an
    acrobatics circumstance. A board has no openings -- there is nothing
    between two squares -- so the sentence narrows a circumstance that never
    comes up and no acrobatics check is ever rolled in a fight for it to
    modify.

    A very large `c.resist_forced` rather than a flat refusal: the printed
    line is about melee and ranged attacks only, and `_by_hand` is the gate
    that leaves a close burst's shove standing.
    """
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=True)
    c.resist_forced(
        99, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _by_hand(str(ctx.get("power") or "")),
    )


@power(
    "m6568a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m6568a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m6608
# --------------------------------------------------------------------------


@power(
    "m6608a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6608a0(c: Cast) -> None:
    _ends_turn_in_aura(c, 1, 5)


@power(
    "m6608a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.slowed(mode=)",),
)
def m6608a1(c: Cast) -> None:
    """The whole of this row is a condition that lands on one mode only.

    Slowed caps a creature's speed, and the engine applies it to the creature
    rather than to a way of moving; `c.ignore_condition(Condition.SLOWED)`
    would waive it outright, which is a creature immune to being slowed rather
    than one whose feet still work.
    """


@power(
    "m6608a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 4),
)
def m6608a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6608a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6608a3(c: Cast) -> None:
    """A walk through a crowd that answers both ways.

    `c.overrun` is the only verb that says who was walked through, which is
    what "each enemy whose space it enters for the first time" needs; the set
    is what "first time" means. The second clause is a watch that lives for
    the turn: anybody within a square who lands a blow during the run is
    clawed back, and `until=When.EOT` is the printed "during this movement".
    """
    me = c.me
    struck: set[int] = set()

    def answer(ev: Hit) -> None:
        foe = getattr(ev, "attacker", None)
        if ev.target != me or foe is None or foe in struck:
            return
        if distance_between(c.world, me, foe) > 1:
            return
        struck.add(foe)
        c.use_power("m6608a2", on=foe, spend=False)

    watch = c.watch(Hit, answer, until=When.EOT, on=me, label=f"{c.ref} wake")
    for foe in c.overrun():
        if foe in struck:
            continue
        struck.add(foe)
        c.use_power("m6608a2", on=foe, spend=False)
    c.world.effects.end(watch, "the run ended")


@power(
    "m6608a4",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(obscured=)",),
)
def m6608a4(c: Cast) -> None:
    """Heavily obscured is more than sight-blocking terrain -- it is also
    total concealment for anything inside it -- and `c.zone` has one flag,
    which buys the half that stops a line of sight."""
    c.zone(spread({c.here}, 2), blocks_sight=True, until=When.EONT, label=c.ref)


# --------------------------------------------------------------------------
# m6629
# --------------------------------------------------------------------------


@power(
    "m6629a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6629a0(c: Cast) -> None:
    """An aura whose toll is taken at the top of its own turn, and only from
    whoever is off their guard.

    `query.has_combat_advantage` is asked here rather than read off a roll
    because there is no roll: nothing is attacking, so the live `AttackResult`
    the other rows read does not exist and the board is the only witness.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def toll(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for foe in c.enemies():
            if distance_between(c.world, me, foe) > 1:
                continue
            if has_combat_advantage(c.world, me, foe):
                c.flat(5, on=foe)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6629a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
    dropped=("c.contract(ref)",),
)
def m6629a1(c: Cast) -> None:
    """The bite lands; what it leaves behind cannot be recorded.

    The second clause is a disease contracted at the **end of the encounter**,
    with its own stage track -- nothing in a fight carries it and nothing
    outside one exists to carry it to. Named rather than approximated: a
    saving throw rolled now would be a different rule.
    """
    if c.strike():
        c.hit()


@power(
    "m6629a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m6629a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    for mate in _kin_within(c, "m6629", 5, of=victim):
        for sq in sorted(spread(set(squares(c.world, victim)), 1)):
            if c.shift(2, who=mate, to=sq):
                break


@power(
    "m6629a3",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6629a3(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m6659
# --------------------------------------------------------------------------


@power(
    "m6659a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m6659a0(c: Cast) -> None:
    """Both steps are Effect lines and are taken whether or not the bite
    lands."""
    c.shift(1)
    if c.strike():
        c.hit()
        _poison_if_exposed(c, 5)
    c.shift(1)


# --------------------------------------------------------------------------
# m6672
# --------------------------------------------------------------------------


@power(
    "m6672a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6672a0(c: Cast) -> None:
    """A burn rather than extra damage, so `c.ongoing` rather than
    `c.damage`: the printed rider is ongoing 3 poison and the stacking rule
    for ongoing damage of one type is the engine's own."""
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker == me and _had_advantage(ev):
            c.ongoing(3, DamageType.POISON, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m6672a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m6672a1(c: Cast) -> None:
    """The step is ranked `toward=` its own target. The card gives it no
    direction, and m6672a3 is this row followed by m6672a2 at the same
    creature -- so this step lands between the two swings, and unranked it put
    the second out of reach. Ranking only: `World.decide` still sees every
    square."""
    if c.strike():
        c.hit()
    c.shift(1, toward=c.target)


@power(
    "m6672a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m6672a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m6672a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m6672a3(c: Cast) -> None:
    victim = c.target
    c.use_power("m6672a1", on=victim, spend=False)
    c.use_power("m6672a2", on=victim, spend=False)
    if not _armed(c, f"{c.ref} wind"):
        me = c.me

        def hurt(ev: Bloodied) -> None:
            if ev.actor == me:
                c.restore_use(c.ref)

        c.watch(
            Bloodied, hurt, until=When.ENCOUNTER, on=me, once=True,
            label=f"{c.ref} wind",
        )


@power(
    "m6672a4",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m6672a4(c: Cast) -> None:
    """The exemption is the dropped half: everyone **except** this creature is
    blinded by the cloud and blind inside it, and `c.zone(blocks_sight=)` is
    terrain with nothing to carve out of it."""
    _blinding_cloud(c, 1)


# --------------------------------------------------------------------------
# m862
# --------------------------------------------------------------------------


@power(
    "m862a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 1),
)
def m862a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m862a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 3),
)
def m862a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m862a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 1, kind=LIMITED),
)
def m862a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()
    c.shift(1)


@power(
    "m862a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m862a3(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee", "ranged"))


# --------------------------------------------------------------------------
# m863
# --------------------------------------------------------------------------


@power(
    "m863a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 1),
)
def m863a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m863a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d6", 1, kind=LIMITED),
)
def m863a1(c: Cast) -> None:
    """The card prints no duration on the burn, so it is the default a save
    ends -- an ongoing with no ending at all is not a thing the rules have."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m863a2",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m863a2(c: Cast) -> None:
    c.shift(1)


@power(
    "m863a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m863a3(c: Cast) -> None:
    """Melee only here, where the sibling rows name melee and ranged both."""
    _advantage_rider(c, "1d6", ("melee",))
