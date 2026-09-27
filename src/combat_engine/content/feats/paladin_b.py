"""Paladin feats, the second batch.

`paladin.py` holds the first. Almost every row here rides on one of two
class features, and which of the two decides whether the row is writable:

* The mark is `p805`. It is a ref in five of these prerequisites, and
  `f1520` names it by ref in its own benefit line -- so the rows reading
  "damage from that power" are ordinary watchers on `DamageRolled` and
  `DamageApplied`, whose `detail` is the ref that dealt the blow.
* The heal is `p1566`, a ref in four prerequisites. `p7240` and `p7249`
  are the two rows printed beside it and are refs as well.

What is *not* a ref anywhere in the list is the second mark -- the one
handed out as a rider rather than as an action. `marks.burning_mark`
lays it, so a row that **applies** it is writable; a row that waits for
somebody else to apply one is not, because a mark announces itself as a
plain `RelationSet` and nothing tells the two marks apart.

The racial powers in this batch arrive as names rather than refs, which
is the opposite of the avenger's list.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.content.powers.paladin.marks import burning_mark
from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Healed,
    Hit,
    Keyword,
    PowerUsed,
    Relation,
    SavingThrow,
    SurgeSpent,
    Trigger,
    TurnStart,
    When,
    Window,
    ally_within,
    distance,
    leaves_me_out,
    power,
)
from combat_engine.engine.components import Gear, Position, Powers
from combat_engine.engine.dsl import REGISTRY, get
from combat_engine.engine.query import allies

#: The paladin's mark, by ref. Named in five of these prerequisites and
#: in f1520's own benefit, so the rows below are not guessing at it.
MARK = "p805"
#: The heal, by ref, and the two rows printed alongside it.
HEAL = "p1566"
#: A racial power the benefit names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)

DEFENCES = (AC, FORT, REF, WILL)


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _beside_bloodied_ally(c: Cast, who: int | None = None) -> bool:
    """Is that creature standing next to a bloodied ally of the paladin?"""
    me = c.me
    subject = me if who is None else who
    return any(
        friend != subject
        and c.bloodied(friend)
        and c.adjacent_to(subject, friend)
        for friend in allies(c.world, me)
    )


# -- riders on the mark's own damage ---------------------------------------


@power("f1520", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1520(c: Cast) -> None:
    """Retypes the mark's bite. `DamageRolled` carries a mutable `dtype`
    and is announced before anything reads resistance off it, so the
    swap lands where the printed "choose each time" wants it -- once per
    payment rather than once for the fight."""
    owner = c.me
    choices = [
        DamageType.ACID,
        DamageType.COLD,
        DamageType.FIRE,
        DamageType.LIGHTNING,
        DamageType.THUNDER,
    ]

    def retype(ev: DamageRolled) -> None:
        if ev.source != owner or ev.detail != MARK:
            return
        if ev.dtype is not DamageType.RADIANT:
            return
        picked = c.choose(choices, "change the damage type to", optional=True)
        if picked is not None:
            ev.dtype = picked

    c.watch(DamageRolled, retype, until=When.ENCOUNTER, on=owner,
            window=Window.BEFORE, label=c.ref)


@power("f1544", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1544(c: Cast) -> None:
    """The extra is printed radiant and rides as radiant without
    `c.bonus` needing a type it does not take: the only damage this gate
    matches is the mark's own, which is radiant already, so the bonus
    goes into that roll rather than beside it."""
    c.bonus(
        "damage", c.str_mod, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == MARK,
    )


@power("f2205", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2205(c: Cast) -> None:
    """"If you are bloodied" is asked per payment rather than once, so
    the gate reads the paladin's own hit points at the moment the mark
    bites."""
    me = c.me
    c.bonus(
        "damage", c.con_mod, on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == MARK and c.bloodied(me),
    )


@power("f2004", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2004(c: Cast) -> None:
    """`DamageApplied` rather than `DamageRolled`: "takes damage" is what
    came off hit points, and a blow entirely absorbed is not one."""
    me = c.me

    def bite(ev: DamageApplied) -> None:
        if ev.source == me and ev.detail == MARK and ev.amount > 0:
            c.slowed(on=ev.target, until=When.EONT)

    c.watch(DamageApplied, bite, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2013", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2013(c: Cast) -> None:
    """Vulnerability of one type, so the amount is handed a `dtype`
    rather than left to stand against everything."""
    me = c.me

    def bite(ev: DamageApplied) -> None:
        if ev.source != me or ev.detail != MARK or ev.amount <= 0:
            return
        if c.marked(on=ev.target, by=me):
            c.vulnerable(5, DamageType.NECROTIC, on=ev.target, until=When.SOTNT)

    c.watch(DamageApplied, bite, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2734", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2734(c: Cast) -> None:
    """"It grants combat advantage" with nobody named is everyone, which
    the relation cannot say in one go -- `to="allies"` lays it once per
    beneficiary on a single hold so they all end together."""
    me = c.me

    def bite(ev: DamageApplied) -> None:
        if ev.source == me and ev.detail == MARK and ev.amount > 0:
            c.grants_advantage(on=ev.target, until=When.SOTNT, to="allies")

    c.watch(DamageApplied, bite, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2909", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.class_feature()", "c.feature_ability()"))
def f2909(c: Cast) -> None:
    """Swaps which ability modifier the two marks pay out from. The
    second mark is named in prose and has no ref at all; the first has
    one, and it still cannot be said, because the number is worked out
    inside `p805`'s own closure and nothing reaches into it."""


# -- what a marked creature owes -------------------------------------------


@power("f2749", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2749(c: Cast) -> None:
    """The same sentence a defender's mark is built on, so it asks it the
    same way: `leaves_me_out` reads the whole target list of the one use
    rather than this announcement's target, and a burst that caught the
    paladin does not count."""
    me = c.me

    def strayed(ev: AttackDeclared) -> None:
        if not c.marked(on=ev.attacker, by=me):
            return
        if not leaves_me_out(c.world, me, ev):
            return
        c.penalty("save", 2, on=ev.attacker, until=When.SOTNT)

    c.watch(AttackDeclared, strayed, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f1530", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1530(c: Cast) -> None:
    """A defence gate reads `attacker` off the attack context, which is
    the one thing the damage context does not carry -- so "against
    creatures marked by you" is askable here and would not have been on
    the other side."""
    me = c.me

    def from_my_mark(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.marked(on=who, by=me)

    for friend in [a for a in allies(c.world, me) if a != me]:
        for defence in DEFENCES:
            c.bonus(defence, 1, on=friend, until=When.ENCOUNTER,
                    when=from_my_mark)


@power("f3083", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_sanction()",))
def f3083(c: Cast) -> None:
    """Slides an enemy the moment the second mark lands on it. A mark is
    announced -- `Relations.set` emits `RelationSet` -- but both of the
    paladin's marks and every other class's are the one relation, so
    there is no way to tell which of them just happened."""


# -- the heal, and whose surge value counts --------------------------------


@power("f1554", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1566 or p7249 on an ally",
       on=(
           Trigger(PowerUsed, _used(HEAL), "you use p1566"),
           Trigger(PowerUsed, _used("p7249"), "you use p7249"),
       ))
def f1554(c: Cast) -> None:
    """Resistance to *all* damage, which `c.resist` says with no type
    rather than with a list of every type there is. Both printed rows
    are refs, so both halves of the "or" are declared."""
    for who in c.trigger.targets:
        c.resist(c.str_mod, on=who, until=When.EONT)


@power("f2295", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1566",
       on=Trigger(PowerUsed, _used(HEAL), "you use p1566"))
def f2295(c: Cast) -> None:
    """Half the paladin's level, rounded down, which is what "one-half
    your level" means everywhere it is printed."""
    for who in c.trigger.targets:
        c.resist(5 + c.level // 2, DamageType.FIRE, on=who,
                 until=When.ENCOUNTER)


@power("f2735", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1566 or p7240",
       on=(
           Trigger(PowerUsed, _used(HEAL), "you use p1566"),
           Trigger(PowerUsed, _used("p7240"), "you use p7240"),
       ))
def f2735(c: Cast) -> None:
    """"The end of his or her next turn" is the *ally's* turn, so
    `EOTNT` and not `EONT`."""
    for who in c.trigger.targets:
        c.conceal(on=who, until=When.EOTNT)


@power("f2872", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1566 on an ally",
       on=Trigger(PowerUsed, _used(HEAL), "you use p1566"))
def f2872(c: Cast) -> None:
    """"Rather than his or her own" is a substitution, not an addition,
    and `Healed` is announced with a mutable `amount` before the hit
    points go on -- which is the one seam where the swap can be made
    without clawing the surplus back off `Health` afterwards.

    `PowerUsed` fires above the body, so a watcher armed here is live
    while that body heals. The latch is a list rather than
    `c.watch(once=True)`: mutating an event emits nothing, so the
    once-guard would never see the handler do anything and the hold
    would sit there for the rest of the turn.
    """
    me = c.me
    mine = c.surge_value(me)
    done: list[int] = []

    def swap(ev: Healed) -> None:
        if done or ev.source != me or ev.target == me:
            return
        done.append(1)
        if mine > ev.amount:
            ev.amount = mine

    c.watch(Healed, swap, until=When.EOT, on=me, window=Window.BEFORE,
            label=c.ref)


@power("f3088", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3088(c: Cast) -> None:
    """The same substitution as f2872 over every power rather than one.

    `Healed` carries no power ref, so "a power that lets an ally spend a
    surge" is recognised by what such a power always pays: exactly that
    ally's surge value. A heal from the paladin of any other size is
    left alone, which is the printed distinction between this and an
    ordinary cure.
    """
    me = c.me

    def bump(ev: Healed) -> None:
        if ev.source != me or ev.target == me:
            return
        theirs = c.surge_value(ev.target)
        mine = c.surge_value(me)
        if ev.amount == theirs and mine > theirs:
            ev.amount = mine

    c.watch(Healed, bump, until=When.ENCOUNTER, on=me, window=Window.BEFORE,
            label=c.ref)


@power("f1559", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, lambda w, me, ev: ev.actor == me,
                  "you spend a healing surge"))
def f1559(c: Cast) -> None:
    """`SurgeSpent` is emitted from every site that decrements a pool,
    so this catches a second wind as readily as a heal."""
    if c.wis_mod > 0:
        c.resist(c.wis_mod, on=c.me, until=When.SONT)


# -- channel divinity, and the save it grants ------------------------------


@power("f1750", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1746",
       on=Trigger(PowerUsed, _used("p1746"), "you use p1746"))
def f1750(c: Cast) -> None:
    """"The saving throw granted by your use of p1746" is not something
    a `SavingThrow` says about itself. It is identified by *when*: the
    row arms a one-shot listener off `PowerUsed`, which fires above the
    body, so the next save that row's own body rolls is the one."""
    me = c.me
    who = c.trigger.targets[0] if c.trigger.targets else None
    if who is None or who == me or who not in allies(c.world, me):
        return
    done: list[int] = []

    def shook_it(ev: SavingThrow) -> None:
        if done or ev.actor != who or not ev.saved:
            return
        done.append(1)
        if c.may("spend a healing surge", who=who):
            c.surge(on=who)

    c.watch(SavingThrow, shook_it, until=When.EOT, on=me, label=c.ref)


@power("f3085", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1746",
       on=Trigger(PowerUsed, _used("p1746"), "you use p1746"))
def f3085(c: Cast) -> None:
    """The failure half of f1750's arrangement, and the payout is a use
    of the group rather than of a row.

    "One of these per encounter" is `Power.group`, and `dsl._group_spent`
    refuses a sibling while any of them has been spent -- so handing the
    spent siblings back **is** the additional use, exactly one of them,
    without inventing a counter the engine does not keep.
    """
    me = c.me
    who = c.trigger.targets[0] if c.trigger.targets else None
    if who is None:
        return
    done: list[int] = []

    def failed(ev: SavingThrow) -> None:
        if done or ev.actor != who or ev.saved:
            return
        done.append(1)
        for defence in DEFENCES:
            c.bonus(defence, 2, on=who, until=When.EOTNT)
        held = c.world.get(me, Powers)
        if held is None:
            return
        for ref in list(held.all):
            row = REGISTRY.get(ref)
            if row is not None and row.group == CHANNEL_DIVINITY:
                c.restore_use(ref)

    c.watch(SavingThrow, failed, until=When.EOT, on=me, label=c.ref)



@power("f2756", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1747",
       on=Trigger(PowerUsed, _used("p1747"), "you use p1747"))
def f2756(c: Cast) -> None:
    """Raising a number another row lays, written as a second untyped
    modifier of the same duration: untyped bonuses add, so the pair come
    to the printed total. `PowerUsed` fires above that row's body, which
    is why laying this first is safe."""
    c.bonus("damage", 4, on=c.me, until=When.SONT)


@power("f3084", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_feature_power()",))
def f3084(c: Cast) -> None:
    """Rides on using a power of one named class feature. The feature
    has a ref, but which rows *belong* to it is not recorded anywhere,
    so there is no set to watch for -- the same gap `f1502` names."""


@power("f3089", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.uncrit()",))
def f3089(c: Cast) -> None:
    """Gives a critical back in exchange for a surge. The whole benefit
    hangs off the exchange, so the healing half cannot land on its own:
    nothing turns a critical into an ordinary hit after it has rolled."""


# -- the bloodied ally -----------------------------------------------------


@power("f2116", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2116(c: Cast) -> None:
    """"While" -- so the adjacency is asked per damage roll rather than
    once when the fight starts, because both the paladin and the ally
    move."""
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _beside_bloodied_ally(c),
    )


@power("f1550", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1550(c: Cast) -> None:
    """"You or your target": the attack context carries `target`, so the
    second half is askable. It would have been silently false on the
    damage side, which carries the key but is consulted too late to move
    an attack roll."""
    def beside(ctx: dict[str, Any]) -> bool:
        if _beside_bloodied_ally(c):
            return True
        foe = ctx.get("target")
        return foe is not None and _beside_bloodied_ally(c, foe)

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=beside)


@power("f3090", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an adjacent ally is bloodied or drops to 0 hit points",
       on=(
           Trigger(Bloodied, ally_within(1), "an adjacent ally is bloodied"),
           Trigger(Dropped, ally_within(1), "an adjacent ally drops"),
       ))
def f3090(c: Cast) -> None:
    """Both printed halves are declared: `Bloodied` and `Dropped` name
    their subject `actor`, which is what `ally_within` reads. The square
    is taken before the slide, because "the ally's vacated square" only
    exists once the ally has left it."""
    friend = c.trigger.actor
    pos = c.world.get(friend, Position)
    if pos is None:
        return
    vacated = pos.square
    if c.slide(1, on=friend):
        c.shift(1, to=vacated)


# -- standing on your own two feet -----------------------------------------


@power("f1516", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you succeed on a saving throw",
       on=Trigger(SavingThrow,
                  lambda w, me, ev: ev.actor == me and ev.saved,
                  "you succeed on a saving throw"))
def f1516(c: Cast) -> None:
    """"Your next attack roll" is `once=True`, which spends the bonus on
    the roll that used it rather than on the first roll of any kind."""
    c.bonus("attack", 2, on=c.me, until=When.EONT, once=True)


@power("f3086", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3086(c: Cast) -> None:
    """A shield bonus the paladin hands out rather than takes.

    Both halves of the Requirement are columns on `Gear`, so they are
    read once when the fight starts. Adjacency and consciousness are not
    -- they change inside a round -- so they are asked per attack, off
    the defence context the gate is handed.
    """
    me = c.me
    gear = c.world.get(me, Gear)
    if gear is None or not gear.shield or gear.armour != "plate":
        return
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            AC, 1, on=friend, until=When.ENCOUNTER, kind="shield",
            when=lambda ctx, who=friend: (
                c.adjacent_to(me, who)
                and not c.is_(Condition.UNCONSCIOUS, on=me)
            ),
        )


@power("f3087", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3087(c: Cast) -> None:
    """Two skill bonuses and nothing else."""


@power("f2923", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2923(c: Cast) -> None:
    """Two numbers of one kind, so the larger wins and the pair say the
    printed "instead".

    The Heal bonus is a skill bonus and out of combat, as every other
    one in the tree is. The rest is combat: both associated rows are
    refs, the weapon is a column on `Gear`, and the distance is measured
    against where the turn began -- which nothing records, so a
    `TurnStart` watcher keeps it.
    """
    me = c.me
    began: dict[int, Any] = {}

    def started(ev: TurnStart) -> None:
        if ev.actor == me:
            began[me] = c.here

    def travelled() -> bool:
        origin = began.get(me)
        pos = c.world.get(me, Position)
        return origin is not None and pos is not None and \
            distance(origin, pos.square) > 2

    def landed(ev: Hit) -> None:
        if ev.attacker != me or ev.power not in ("p1724", "p1567"):
            return
        gear = c.world.get(me, Gear)
        if gear is None or gear.main is None or gear.main.ref != "w:longsword":
            return
        if c.turn_of() != me:
            return
        c.bonus("save", 2, on=me, until=When.EOT, kind="power")
        c.bonus("save", 5, on=me, until=When.EOT, kind="power",
                when=lambda ctx: travelled())

    c.watch(TurnStart, started, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=c.ref)


# -- the multiclass pair ---------------------------------------------------


@power("f2125", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2125(c: Cast) -> None:
    """"Attack powers" excludes the utilities, which the header says:
    `Power.attack` is None for a row that does not roll one. The paragon
    half of the sentence is out of scope, not a gap -- the project stops
    at 10."""
    me = c.me

    def mine_against_cursed(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power", ""))
        foe = ctx.get("target")
        return (
            row is not None and row.cls == "paladin" and row.attack is not None
            and foe is not None
            and c.world.relations.holds(Relation.CURSED_BY, me, foe)
        )

    c.bonus("damage", 2, on=me, until=When.ENCOUNTER,
            when=mine_against_cursed)


@power("f2126", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f2126(c: Cast) -> None:
    """Bigger dice for the other class's own extra damage. Both
    conditions are readable -- the mark is a relation and so is the
    curse -- but the dice are a literal inside `features.extra_damage`
    and nothing outside that row chooses them."""


# -- racial, and named in prose --------------------------------------------


@power("f1514", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1514(c: Cast) -> None:
    """An ally's melee damage bonus against whatever a racial power was
    just spent on. The power is named in prose with no ref, so there is
    nothing to watch."""


@power("f1517", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1517(c: Cast) -> None:
    """The second mark on every enemy a racial power caught. Laying the
    mark is `marks.burning_mark` and would be one line; the racial power
    is a name."""


@power("f1543", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1543(c: Cast) -> None:
    """Same shape as f1517 against a single target, and the same gap."""


@power("f1560", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2485",
       on=Trigger(PowerUsed, _used("p2485"), "you use that racial power"))
def f1560(c: Cast) -> None:
    """This racial power *is* a ref, unlike the three above.
    `c.save(against="ongoing")` picks the burn rather than whichever
    save-ends hold happens to be first, which is the printed clause."""
    me = c.me
    for friend in c.within(5, side="ally"):
        if friend != me:
            c.save(on=friend, against="ongoing")


@power("f2128", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.basic_ability()",))
def f2128(c: Cast) -> None:
    """Replaces a racial power with the card below, which `c.grant_row`
    says. The ability swap on melee basic attacks is dropped: nothing
    changes which modifier a basic attack rolls."""
    c.grant_row("f2128b", on=c.me, until=When.ENCOUNTER)


@power("f2128b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=EACH_ENEMY,
       keywords=[Keyword.DIVINE])
def f2128b(c: Cast) -> None:
    """The card of f2128. The second mark is a helper rather than a bare
    `c.mark`, because the radiant bite for attacking somebody else is
    half of what the mark is."""
    burning_mark(c, until=When.EONT)
