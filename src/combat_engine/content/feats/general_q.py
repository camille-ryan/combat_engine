"""General feats, the seventeenth batch: the double-weapon chains, the
martial associated-power riders, and the psionic power-point tail.

Four shapes account for nearly all of it.

**The swap chain.** Eleven rows here read "you swap one of your level N
powers for X", and every one of them is a parent with a card beside it.
The parent hands the card over with `c.grant_row` and carries
`chargen.power_swap()` for the half nobody can write: giving a power
*up* is a build-time exchange, not something a fight can say. Each card
prints a Requirement naming one weapon, so they use the `exotic.py`
gate -- `holding(world, eid, ...)` -- and every one of them will report
UNUSED. That is a chassis gap (chargen deals no such weapon) rather
than a row gap, and it is the same one `exotic.py` states at length.

**The associated-power rider.** Ten martial feats print a skill bonus
*and* "when you use a power associated with this feat and hit an enemy
with it, ...". A row declared with `on=Trigger(...)` never lays its
standing modifiers, so these are traits: the bonus is laid at arm time
and `c.watch(Hit, ...)` carries the rider. Three of them were written
with the rider `dropped` because the spec carried no Associated Powers
line; **it carries one now** for all three, and they are finished.

**"You can spend 1 power point to ..."** is writable: `c.points()` asks
whether there is one and `c.spend_points(1)` takes it. Five of the
psionic feats here are finished for that reason alone. Handing one
*back* turns out to be writable too -- `PowerPoints.points` is a plain
field and `c.transfer_points` already adds to it, so `f3295` and
`f3389` are written against the component. What is still absent is
reading a pool back down to zero (`c.on_points_spent()`) and the
printed "not until an extended rest", which is a rule about rests.

**Theme powers, and what naming the ref bought.** Eighteen rows here ride
on nine theme powers that no build imported, and each was marked with the
import gap *and* the ref it would watch. The nine are declared rows now,
so the marker went red and all eighteen are written against them. Sixteen
are finished; the two that fire on dismissing a conjuration are re-aimed,
because the row they ride on never dismisses one and nothing announces it.

They are traits carrying `c.watch` rather than rows with `on=Trigger`, the
same shape as the ten associated-power riders above: a declared trigger
does not arm at the start of a fight, and three of these hang two clauses
off one event.

`p12315` and the rest are ids, not names: what the id is called is still
nobody's business here.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.warlock import BOON_REGAIN
from combat_engine.content.powers.monk.level_0 import FLURRIES
from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Keyword,
    Melee,
    Ranged,
    SavingThrow,
    SecondWind,
    Swap,
    Trigger,
    UpTo,
    Usage,
    When,
    Window,
    about_me,
    cursed_by_me,
    get,
    grid,
    power,
    targets_me,
)
from combat_engine.engine.components import Health, PowerPoints
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.events import (
    ActionPointSpent,
    ActionSpent,
    AttackDeclared,
    AttackRolled,
    ConditionApplied,
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    EffectApplied,
    Hit,
    Miss,
    MoveEnd,
    MoveStart,
    PowerResolved,
    PowerUsed,
    SkillCheck,
)
from combat_engine.engine.query import (
    alive,
    allies,
    distance_between,
    holding,
    squares,
    team,
)

#: A power the spec names in prose and that has no ref **anywhere** --
#: not in the tree, not in the compendium. Nothing can watch it and
#: nothing will import it either.
#: **Re-aimed to the mechanic, not the ref.** Both rows that used this were
#: marked "the brief prints a name and gives no ref", which is true -- the
#: compendium holds no row of any kind by that name -- but it is not what
#: would unblock them. Their clauses ride on the *act* of defiling, and
#: `c.on_defiling()` is the hook two other rows already wait on. A ref would
#: not help; the hook would.
PROSE = ("c.on_defiling()",)
#: A rider on a *set* of powers the card names by category rather than by ref.
#:
#: **One row, not two, and the symbol is probably no longer the right one.**
#: The ten-row half (`f3247`) is written: `_wild_talents` below filters
#: `dsl.REGISTRY` by `cls`, which is what `items/misc.py` has always done for
#: an arcane class's attack rows, so nothing was missing there. `f3209` keeps
#: this marker because it is still refused, but read its docstring before
#: going looking for the filter: what blocks it is the ref its own spec
#: prints, not any enumeration.
#:
#: **Re-aimed off `etl.build.CLASSES`, which was never able to go green.** That
#: marker said the powers were missing from `data/game.db` -- and they are not:
#: the eleven theme classes (`x7_661` and the rest) and `wild talent` are all in
#: the `power` table today, so the import gap it named is closed. Worse, the
#: symbol it named *already existed*, so `todo.py` could only ever report it
#: arrived, which is exactly what it did. A marker has to name something absent
#: or it is not a marker. Nothing enumerates the registry by class, so that is
#: the gap, and it is one gap for both rows.
NO_IMPORT = ("dsl.powers_of(cls)",)
#: "You swap one of your level N powers for this one." The card is handed
#: over; giving a power up is a build-time exchange.
SWAP = ("chargen.power_swap()",)
#: Augmenting a power from outside its own card.
#: **Re-aimed.** `dsl.use(augment=)` arrived -- a row declares its
#: augments in its own header and the spend is settled before targeting --
#: and none of these is that shape. Every one of them expends the
#: warlock's fell might on a power whose card prints no Augment line,
#: which is an offer laid on another row from outside it. Same symbol the
#: psionic aspect dailies in `docs/blocked.json` already name.
#: **Expending something other than power points to augment a row.** Six
#: warlock feats print "you can also expend your fell might to augment any
#: power associated with this feat", and seven more print "when you augment
#: p12887, you can forgo the extra damage the augment would deal to instead
#: <effect>" -- which needs that augment to exist before it can be forgone.
#:
#: **Re-pointed from `c.lend_augment(ref, clause)`, which is implemented.**
#: That verb lends a *clause* and four rows now use it (#507). These
#: thirteen want a different thing wearing the same name: a **resource**
#: standing in for power points. The resource itself is built --
#: `c.spend_charge` on a key the owning row coins, which is what
#: `c.fell_might()` was standing in for (#529) -- and spending it *on an
#: augment* is the further step that did not arrive with it. So this symbol
#: is still the gap and is now the only one.
#:
#: The "forgo the extra damage" half is `c.pre_empt`, which exists -- so
#: naming only this one is correct: it is the earliest gap, and the one
#: without which the rest says nothing.
AUGMENT = ("c.augment_with(resource)",)
#: "Choose a power granted by <feature>" -- the features are rows now,
#: and so are their options, but every option refuses itself off
#: `c.build` on its first line. Handing one to a character of another
#: class hands over a row that returns immediately, and nothing puts a
#: character on a leg of a class it did not take.
BORROW = ("c.set_build()",)

MARTIAL = [Keyword.MARTIAL]
WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
PSIONIC = [Keyword.PSIONIC]
WALKED = ("walk", "shift", "run")


# -- small shared questions -------------------------------------------------


def _wielding(what: str):  # noqa: ANN202
    """A printed Requirement naming one weapon, by **ref**.

    **It was `m5466a0` on all four rows, which is a monster power.** That
    ref shares the weapon's printed name, so a name-to-ref resolution found
    the wrong table -- and `holding` matches a group, a property, a category
    or the weapon's slug, none of which a monster power ref can ever be. The
    Requirement was false for every creature in the game, and the line this
    docstring used to carry ("False for every character `chargen` can build
    today") read that as a chargen limitation rather than a wrong argument.

    `w3711` is the weapon. `query.holding` matches a ref as of this change,
    which is what lets a row name one weapon without writing the printed
    name into a tracked file -- the reason the wrong ref was reached for.
    `w3712` is the same weapon's second end and is not what "wielding" asks
    about."""

    def gate(world, eid: int) -> bool:  # noqa: ANN001
        return bool(holding(world, eid, what))

    return gate


#: Raised once per fight per feat. A trait is armed at the start of every
#: fight and the sentence is about the character sheet, so the pool must go
#: up once however many fights it sees -- `feats/paladin.py` holds the same
#: latch for the same reason.
_SURGES_RAISED: dict[tuple[int, str, int], bool] = {}
#: The same latch for the point `f3389` hands over.
_POINT_GRANTED: dict[tuple[int, str, int], bool] = {}


def _one_more_surge(c: Cast) -> None:
    """"Your number of healing surges increases by one."

    `Health.max_surges` is the ceiling a rest refills to, no `Cast` method
    writes it, and `feats/paladin.py` already raises it from content. The
    surge itself is handed over beside it: raising the ceiling alone leaves
    the character with no more to spend than it had.
    """
    key = (id(c.world), c.ref, c.me)
    health = c.world.get(c.me, Health)
    if health is None or _SURGES_RAISED.get(key):
        return
    _SURGES_RAISED[key] = True
    health.max_surges += 1
    c.regain_surge(1, on=c.me)


def _wild_talents() -> list[str]:
    """The ten rows the compendium files under that category, by ref.

    A `cls` value like any other, so this is the read `items/misc.py` makes
    for an arcane class's attack rows. Sorted, so two characters offered the
    choice see the same order.
    """
    return sorted(
        ref for ref, row in REGISTRY.items() if row.cls == "wild talent"
    )


def _swap(ref: str, card: str, trade: Swap) -> None:
    """The parent half of a swap chain: the card, and what it costs.

    Both halves of the printed exchange. The body hands the card over;
    `trade` is what goes back, and `chargen.power_swap` takes it when the
    character is built -- which is where a swap happens, a fight opening
    with the hand already dealt.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, swap=trade)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card} in place of a power of that level."


def _melee(ref: str) -> bool:
    p = get(ref)
    return p is not None and p.reach is not None and p.reach.kind == "melee"


def _best_of_two(c: Cast) -> int:
    """"Strength or Dexterity" -- the header names one, this is the pick."""
    return max(c.str_mod, c.dex_mod)


def _on_hit_with(c: Cast, refs: tuple[str, ...], fn,  # noqa: ANN001
                 *, once: bool = False) -> None:
    """"When you use a power associated with this feat and hit an enemy."

    A trait rather than a declared trigger, because each of these feats
    also prints a standing skill bonus and a body under `on=` runs only
    when the trigger fires.

    `once` is `c.watch`'s own, which means "fire once" and not "live for
    one event" -- it reads the log to see whether the handler did
    anything, so a `Hit` with the wrong power does not spend the hold.
    That is what a printed "once per encounter" needs.
    """

    def rider(ev: Any) -> None:
        if ev.attacker == c.me and ev.power in refs:
            fn(ev)

    c.watch(Hit, rider, on=c.me, until=When.ENCOUNTER, once=once)


def _resolving(c: Cast, ref: str):  # noqa: ANN202
    """Is `ref` between its own `PowerUsed` and `PowerResolved` right now?

    "Who shifts as a result of the power" names creatures the body moved,
    and neither event alone can say it: `PowerUsed` is announced above the
    body, so nothing has happened yet, and `PowerResolved` below it, so the
    move is over and unattributed. The pair brackets everything the body
    emits, which is exactly the set the clause means.
    """
    live = [False]

    def opened(ev: Any) -> None:
        if ev.actor == c.me and ev.power == ref:
            live[0] = True

    def closed(ev: Any) -> None:
        if ev.actor == c.me and ev.power == ref:
            live[0] = False

    c.watch(PowerUsed, opened, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} open")
    c.watch(PowerResolved, closed, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} shut")
    return lambda: live[0]


def _after_hits_with(c: Cast, ref: str, fn) -> None:  # noqa: ANN001
    """"When you hit with `ref`", paid out once the row has finished.

    A `Hit` fires above the rest of the body, so a clause printed as
    happening at the end of a shove, or after the attack, cannot be paid
    there -- the shove has not happened yet. The creatures hit are collected
    and spent on `PowerResolved`, which is the first point at which they are
    standing where the row left them.
    """
    caught: set[int] = set()

    def landed(ev: Any) -> None:
        if ev.attacker == c.me and ev.power == ref:
            caught.add(ev.target)

    def done(ev: Any) -> None:
        if ev.actor != c.me or ev.power != ref:
            return
        for who in sorted(caught):
            fn(who)
        caught.clear()

    c.watch(Hit, landed, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} landed")
    c.watch(PowerResolved, done, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} after")


def _spot(c: Cast, who: int) -> tuple[int, int] | None:
    return next(iter(sorted(squares(c.world, who))), None)


def _who_rolled(ev: Any) -> int | None:
    """Whose roll an immediate answered. `AttackRolled` says `attacker`."""
    if ev is None:
        return None
    who = getattr(ev, "actor", None)
    return getattr(ev, "attacker", None) if who is None else who


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _my_use(ref: str):  # noqa: ANN202
    """`PowerUsed` names its subject `actor`, which `by_me` never reads."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _hit_with(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


def _point(c: Cast) -> bool:
    """"You can spend 1 power point to ..." -- the whole of the option."""
    return bool(c.points()) and c.may("spend a power point") and bool(
        c.spend_points(1)
    )


# -- the untiered head of the list ------------------------------------------


@power("f3176", level=1, cls="", usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3176(c: Cast) -> None:
    """Two-way speech with anything nearby that has a language. Nothing
    in a fight turns on being able to say something."""


@power("f3177", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3177(c: Cast) -> None:
    """Four lore bonuses about one subject matter. Nothing on a board rolls
    Arcana, History or Dungeoneering, and the only Insight a fight reads is
    the passive DC of a bluff -- never a question about a creature's
    origin. Narrative, not unwritten."""


@power("f3178", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3178(c: Cast) -> None:
    """The save context carries the keywords of the row that laid the
    hold. Psychic is also a damage type, so an ongoing psychic burn laid
    by a row that prints no keyword still counts."""
    c.bonus(
        "save", 2, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(
            {Keyword.CHARM, Keyword.ILLUSION, Keyword.PSYCHIC}
            & set(ctx.get("keywords", ()))
        ) or ctx.get("dtype") is DamageType.PSYCHIC,
    )


@power("f3179", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="a creature you can see succeeds on a skill check",
       on=Trigger(SkillCheck, lambda w, me, ev: (
           ev.success and alive(w, ev.actor)
           and distance_between(w, me, ev.actor) <= 10
       ), "a creature you can see succeeds on a skill check"))
def f3179(c: Cast) -> None:
    """"Any creature you can see" is taken as anything alive within
    sight range; nothing computes visibility for a bystander. The bonus
    is to *that* skill, which `c.bonus("skill:<name>")` says directly."""
    c.bonus(f"skill:{c.trigger.skill}", 2, on=c.me, until=When.EONT,
            kind="feat")


# -- the heroic body --------------------------------------------------------


@power("f3180", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3180(c: Cast) -> None:
    """"Affected by" is read as the ally p11778 actually moved: the row
    offers a choice and only one half of it shifts anybody, so the window
    between its own two announcements is what names them.

    The grant is held on the enemy, because that is whose side of the
    relation it is -- `to=` says who reads it."""
    during = _resolving(c, "p11778")

    def stepped(ev: MoveEnd) -> None:
        if not during() or ev.kind_ != "shift" or ev.actor not in c.allies():
            return
        for foe in c.within(1, of=ev.actor, side="enemy"):
            c.grants_advantage(on=foe, to=ev.actor, until=When.EONT)

    c.watch(MoveEnd, stepped, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} step")


@power("f3182", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3182(c: Cast) -> None:
    """A trait arms before the first turn, so "during the first round"
    is `When.EONT` measured from arming -- it lapses at the end of the
    character's own first turn, which is the round it is printed for.

    `c.initiative` moves the creature in the order rather than laying a
    modifier, and takes no `kind`; its own docstring says why a bonus
    cannot express an initiative bonus at all."""
    c.initiative(2, on=c.me)
    c.bonus("attack", 1, on=c.me, until=When.EONT)
    c.bonus("speed", 1, on=c.me, until=When.EONT)


@power("f3183", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3183(c: Cast) -> None:
    """"Instead of 2 squares" is the shover's own `"forcing"` key, which
    `movement.forced` reads with the ref and the kind of shove in its
    context. A second `c.push` would have been the wrong shape: it measures
    its direction from wherever the first one left the target."""
    c.bonus("forcing", c.con_mod, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: (ctx.get("power") == "p11868"
                              and ctx.get("how") == "push"))


_swap("f3184", "f3184b", Swap(6, utility=True))


@power("f3184b", level=1, cls="", usage=ENCOUNTER, action=MOVE,
       reach=Melee(1), target=ONE_CREATURE, keywords=MARTIAL,
       requires=_wielding("w3711"),
       requires_text="wielding the weapon this chain names")
def f3184b(c: Cast) -> None:
    """The target comes along, which is a pull of however far the move
    actually went -- a pull keeps it next to you, which is what
    "pulling the target with you" means on a board of squares."""
    foe = c.target
    if foe is None:
        return
    if not (c.is_(Condition.IMMOBILIZED, foe) or c.is_(Condition.PRONE, foe)):
        return
    c.no_provoke(from_=foe, on=c.me, until=When.EOT)
    gone = c.move(c.speed_of())
    if gone:
        c.pull(gone, on=foe)


_swap("f3185", "f3185b", Swap(3, Usage.ENCOUNTER))


@power("f3185b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("w3711"),
       requires_text="wielding the weapon this chain names")
def f3185b(c: Cast) -> None:
    """"You can use f3185c against the target" is a row handed over for
    a turn, which is exactly `c.grant_row`."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.pull(1)
        c.grant_row("f3185c", on=c.me, until=When.SONT)


@power("f3185c", level=1, cls="", usage=ENCOUNTER, action=OPPORTUNITY,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("w3711"),
       requires_text="wielding the weapon this chain names",
       trigger="the target willingly enters a square not adjacent to you",
       on=Trigger(MoveStart, lambda w, me, ev: (
           ev.actor != me and team(w, ev.actor) != team(w, me)
           and ev.kind_ in WALKED
           and distance_between(w, me, ev.actor) <= 1
       ), "an adjacent enemy willingly moves away"))
def f3185c(c: Cast) -> None:
    """`MoveStart`, not `MoveEnd`: the swing is an opportunity action and
    interrupts the step, so it has to be asked while the enemy is still
    within reach. By `MoveEnd` the square it entered is the one that is
    not adjacent and `Melee(1)` refuses the row."""
    foe = c.trigger.actor
    if c.strike(on=foe):
        c.damage(c.w(), on=foe)
        c.prone(on=foe)


_swap("f3186", "f3186b", Swap(9, Usage.DAILY))


@power("f3186b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Ranged(10), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.RELIABLE, Keyword.WEAPON],
       attack=Attack(STR, vs=REF), requires=_wielding("w3711"),
       requires_text="wielding the weapon this chain names")
def f3186b(c: Cast) -> None:
    """Both ends of the weapon land on one roll, so the off-hand dice are
    a second `c.damage` on the same hit rather than a second strike."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.damage(c.w(1, hand="off"))
        c.prone()
        c.immobilized(until=When.SAVE_ENDS)


@power("f3187", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3187(c: Cast) -> None:
    """"Character" is the caster or an ally, and the creature p12338 hit is
    not a candidate -- it is who the invisibility is *from*. `c.invisible`
    sets the relation one watcher at a time, so `to=` is that target and
    nobody else."""

    def landed(ev: Hit) -> None:
        crowd = [w for w in (c.me, *c.within(10, side="ally")) if w != ev.target]
        who = c.choose(crowd) if crowd else None
        if who is not None:
            c.invisible(on=who, to=ev.target, until=When.EONT)

    _on_hit_with(c, ("p12338",), landed)


#: p704 is gone from this list because its clause is written into p704's
#: own body (#550). The watcher still covers the other three.
_F3188 = ("p917", "p992", "p1063")


@power("f3188", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3188(c: Cast) -> None:
    """The shift doubles for one race. The difficult terrain waiver is
    held to the end of the turn because it is scoped to the shift and
    nothing scopes an allowance to one move.

    **The marker said nothing reads a character's race back. It does now.**
    `c.race_of` answers by ref -- `c.race_of(on=ally) == "r4"` is its own
    worked example -- and landed after this row was written, so the
    `c.race()` it waited on had already arrived under a different name.
    Asked inside the rider rather than at arming time, which costs
    nothing and keeps the row honest if a form ever changes the answer.
    """
    c.bonus("skill:acrobatics", 1, on=c.me, until=When.ENCOUNTER, kind="feat")
    c.bonus("skill:athletics", 1, on=c.me, until=When.ENCOUNTER, kind="feat")

    def step(ev: Any) -> None:
        c.ignores_difficult(on=c.me, until=When.EOT)
        c.shift(2 if c.race_of(on=c.me) == "r4" else 1)

    _on_hit_with(c, _F3188, step)


@power("f3189", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_dismiss(ref, fn)",))
def f3189(c: Cast) -> None:
    """**Re-aimed off `etl.build.CLASSES`, and off the ref.** p11804 is a
    declared row now and the ref was not the wait that mattered: its printed
    dismissal is one standard action that banishes the spirit *and* attacks
    from its square, and the attack line is the half p11804 drops -- so
    nothing in the tree ever dismisses the spirit, and no event announces a
    conjuration being dismissed. The payout of a deliberate end is
    `c.endable(then=)`, which a row writes into its own body; a second row
    cannot add a clause to it. That hook is the whole of the gap."""


@power("f3190", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3190(c: Cast) -> None:
    """Lets a named ability ride an action point.

    **Re-aimed off `c.class_feature()`.** It is not a class feature: the
    prerequisite parser files the same ability under `kind = 'power'`
    (six feats share the term), and the compendium holds no row of any
    kind by that name -- no Power, no Feat, no Theme, no Class. So there
    is no ref to import and none to borrow.

    **But a ref is not what this row needs.** The clause rides on the *act* of
    defiling, not on naming the ability, so the gap is the hook --
    `c.on_defiling()`, which two item blocks already wait on -- and the marker
    says that now rather than asking for a ref that cannot exist."""


@power("f3191", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3191(c: Cast) -> None:
    """"At the end of the push" cannot be paid on the `Hit`, which fires
    above the shove -- the target has not moved yet there."""
    _after_hits_with(c, "p11868", lambda who: c.prone(on=who))


_swap("f3192", "f3192b", Swap(6, utility=True))


@power("f3192b", level=1, cls="", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.MARTIAL, Keyword.STANCE],
       requires=_wielding("dragon paw"),
       requires_text="wielding the weapon this chain names")
def f3192b(c: Cast) -> None:
    """`Hit` does not declare `opportunity`; `resolve.attack` sets it as
    a plain attribute afterwards, so the watcher has to `getattr` it."""
    c.stance(on=c.me)

    def bite(ev: Any) -> None:
        if ev.target == c.me and getattr(ev, "opportunity", False):
            c.damage(c.w(1, hand="off"), on=ev.attacker)

    c.watch(Hit, bite, on=c.me, until=When.STANCE)


_swap("f3193", "f3193b", Swap(3, Usage.ENCOUNTER))


@power("f3193b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("dragon paw"),
       requires_text="wielding the weapon this chain names")
def f3193b(c: Cast) -> None:
    """"2[W] if you target only one creature with the secondary attack"
    is read off how many the board actually offers, not off a choice --
    a second adjacent enemy either exists or does not."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
    others = [e for e in c.within(1, side="enemy") if e != c.target][:2]
    dice = 2 if len(others) == 1 else 1
    for who in others:
        if c.strike(on=who, hand="off"):
            c.damage(c.w(dice, hand="off"), c.str_mod, on=who)


_swap("f3194", "f3194b", Swap(9, Usage.DAILY))


@power("f3194b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("dragon paw"),
       requires_text="wielding the weapon this chain names")
def f3194b(c: Cast) -> None:
    """The printed Miss line covers both attacks, so the secondary pays
    half on a miss as well."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.slide(1)
    else:
        c.half_damage(c.w(3), c.str_mod)
    for who in c.within(1, side="enemy"):
        if who == c.target:
            continue
        if c.strike(on=who, hand="off"):
            c.damage(c.w(), c.str_mod, on=who)
            c.push(1, on=who)
            c.prone(on=who)
        else:
            c.half_damage(c.w(), c.str_mod, on=who)


@power("f3195", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3195(c: Cast) -> None:
    """Both halves name where they end, so both are `to=`: a free slide goes
    away from nobody in particular and a free shift does not land beside the
    target. Squares adjacent to an ally are struck out before the choice
    rather than gated afterwards, which is what "to a square that is not"
    says. "After the attack" is p12360's own resolution, by which its
    opening shift has been taken."""

    def after(who: int) -> None:
        spot = _spot(c, who)
        if spot is None:
            return
        beside_ally = {
            sq
            for friend in c.allies()
            if (at := _spot(c, friend)) is not None
            for sq in grid.neighbours(at)
        }
        clear = sorted(
            sq
            for sq in grid.spread({spot}, 2)
            if sq != spot and sq not in beside_ally and not c.in_squares([sq])
        )
        if clear:
            c.slide(2, on=who, to=c.choose(clear))
        spot = _spot(c, who) or spot
        beside = sorted(
            sq
            for sq in grid.neighbours(spot)
            if not c.in_squares([sq]) and grid.distance(c.here, sq) <= 3
        )
        if beside:
            c.shift(3, to=c.choose(beside))

    _after_hits_with(c, "p12360", after)


_F3196 = ("p4368", "p971", "p315", "p1758")


@power("f3196", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3196(c: Cast) -> None:
    """`c.penalty` takes no `kind` and that is the rule, so the -2 is
    written plain."""
    c.bonus("skill:intimidate", 2, on=c.me, until=When.ENCOUNTER,
            kind="feat")

    def cow(ev: Any) -> None:
        c.penalty("attack", 2, on=ev.target, until=When.EONT)

    _on_hit_with(c, _F3196, cow)


@power("f3197", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3197(c: Cast) -> None:
    """"A target granting combat advantage to you" is read off the roll that
    already happened. Asking the board again is too late: a one-shot grant
    has been spent by the time a `Hit` is announced."""

    def landed(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if result is not None and result.advantage:
            c.dazed(on=ev.target, until=When.EONT)

    _on_hit_with(c, ("p12360",), landed)


@power("f3198", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3198(c: Cast) -> None:
    """An attack bonus on whatever an ally's power hands this character.

    `granted_by` is on the attack context now. An *ally's* power, so a
    self-grant is excluded -- a defender punishing an opening hands
    itself a swing and it carries the same field. Asked per roll, since
    who is an ally does not change but who granted does.
    """
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("granted_by", -1) != c.me
            and ctx.get("granted_by", -1) in allies(c.world, c.me)
        ),
    )


_F3199 = ("p10592", "p653", "p1000", "p620")


@power("f3199", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3199(c: Cast) -> None:
    """"You do not grant combat advantage for being flanked" is exactly
    `c.cannot_be_flanked`, which suppresses the flanking grant and leaves
    every other source of advantage alone."""
    c.bonus("skill:insight", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def guard(ev: Any) -> None:
        c.cannot_be_flanked(on=c.me, until=When.SONT)

    _on_hit_with(c, _F3199, guard)


@power("f3200", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_dismiss(ref, fn)",))
def f3200(c: Cast) -> None:
    """**Re-aimed off `etl.build.CLASSES`, and off the ref.** Same wait as
    f3189: p11804 is declared and never dismisses its spirit, because the
    dismissal is the standard-action attack it drops -- and nothing
    announces a conjuration being dismissed for another row to answer."""


@power("f3201", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3201(c: Cast) -> None:
    """Who "becomes invisible as a result of the power" is read off the hold
    the power laid: `c.invisible` labels it with the ref that made it and
    `EffectApplied` carries that label. Nothing else announces a creature
    going unseen to one watcher -- `RelationSet` names the pair and not who
    paid for it.

    The target itself is struck out of "each enemy adjacent to the target":
    `c.within` keeps whatever the circle is centred on."""
    foe = [-1]
    _on_hit_with(c, ("p12338",), lambda ev: foe.__setitem__(0, ev.target))

    def unseen(ev: EffectApplied) -> None:
        if ev.source != c.me or foe[0] < 0 or not ev.label.startswith("p12338"):
            return
        for near in c.within(1, of=foe[0], side="enemy"):
            if near != foe[0]:
                c.invisible(on=ev.target, to=near, until=When.EONT)

    c.watch(EffectApplied, unseen, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} unseen")


@power("f3203", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, )
def f3203(c: Cast) -> None:
    """Adds the reliable keyword to one named row.

    Keywords are header data -- one tuple fixed at import and shared by
    everybody who holds the row -- so this is recorded against the creature
    and merged by `dsl.keywords_of`, which `dsl.use` reads when it decides
    whether a miss spends the power.
    """
    c.counts_as_keyword("p11739", Keyword.RELIABLE)
@power("f3204", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3204(c: Cast) -> None:
    """"That ally" is whoever made the triggering roll, which is the trigger
    the announcement carries and not `ev.targets` -- p12244 is `NO_TARGET`
    and aims itself off its own trigger. `AttackRolled` names its subject
    `attacker` where the other two name it `actor`.

    Read on resolution rather than on use, because the printed clause is
    paid "after that roll is resolved" and `PowerUsed` fires above the body
    that does the modifying."""

    def paid(ev: PowerResolved) -> None:
        if ev.actor != c.me or ev.power != "p12244":
            return
        who = _who_rolled(ev.trigger)
        if who is not None and who in c.allies():
            c.grant_action("shift", FREE, squares_=2, on=who, until=When.EOT)

    c.watch(PowerResolved, paid, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} step")


_swap("f3206", "f3206b", Swap(6, utility=True))


@power("f3206b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=MARTIAL,
       requires=_wielding("gouge"),
       requires_text="wielding the weapon this chain names",
       trigger="you hit an enemy with a gouge",
       on=Trigger(Hit, _i_hit, "you hit an enemy"))
def f3206b(c: Cast) -> None:
    """"To a square adjacent to the enemy" is `toward=` the creature the
    trigger is about: the squares are offered closest-first, so the step
    closes on the one just hit instead of going wherever the decider's
    first option happened to be."""
    c.shift(3, toward=c.trigger.target)


_swap("f3207", "f3207b", Swap(3, Usage.ENCOUNTER))


@power("f3207b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=UpTo(2), keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("gouge"),
       requires_text="wielding the weapon this chain names")
def f3207b(c: Cast) -> None:
    """One or two creatures, so the body runs once each."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.slide(1)
        c.prone()


_swap("f3208", "f3208b", Swap(9, Usage.DAILY))


@power("f3208b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("gouge"),
       requires_text="wielding the weapon this chain names",
       dropped=("c.grab(unbreakable=)",))
def f3208b(c: Cast) -> None:
    """"Cannot stand up" is `c.prone(held=...)`: the condition is pinned
    rather than reapplied, which is the difference between a creature
    that keeps failing to rise and one that never gets the chance.

    What is dropped is the grab's unusual durability -- it survives the
    forced movement that normally breaks it and ends only when you swing
    at somebody else -- and the shift that rides on moving the target.
    `c.grab` has one behaviour and no way to ask for another."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    c.prone(held=When.ENCOUNTER)
    c.grab()


@power("f3209", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=NO_IMPORT)
def f3209(c: Cast) -> None:
    """A mark hung on a set of attacks the card names rather than lists.

    **The filter arrived; the set is still not nameable.** `dsl.REGISTRY`
    can be asked by `cls` -- `_wild_talents` above does it, and `f3247`
    carried this same marker and is written -- so enumerating a class's
    rows is no longer what blocks this.

    What blocks it is the row's own spec. It names `cf:druid-f1s0` as the
    thing whose attacks these are, and that ref is one arm of a fork whose
    whole content is an ability substitution for AC: it prints no attack,
    grants none, and `features/primal_divine.py` skips it deliberately as a
    restatement of `cf:druid-f1`. Nothing ties a set of attack rows to it,
    so there is no set to resolve and the mark has nothing to hang on.
    Referred up rather than guessed at."""


_F3210 = ("p2105", "p10733", "p10889", "p919")


@power("f3210", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3210(c: Cast) -> None:
    """Concealment is a modifier rather than a flag, so "while you have
    concealment" is `c.total("concealment")` -- the same number
    `c.conceal` writes and `resolve.attack` reads."""
    c.bonus("skill:athletics", 3, on=c.me, until=When.ENCOUNTER, kind="feat")

    def cover(ev: Any) -> None:
        if c.total("concealment", on=c.me) <= 0:
            return
        mates = [a for a in c.allies() if c.can_see(a)]
        if not mates:
            return
        friend = c.choose(mates, "who may shift")
        if friend is not None:
            c.grant_action("shift", OPPORTUNITY, on=friend, until=When.EOT)

    _on_hit_with(c, _F3210, cover)


_swap("f3211", "f3211b", Swap(6, utility=True))


@power("f3211b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=MARTIAL,
       requires=_wielding("m5495a1"),
       requires_text="wielding the weapon this chain names",
       trigger="you hit an enemy with the weapon this chain names",
       on=Trigger(Hit, _i_hit, "you hit an enemy"))
def f3211b(c: Cast) -> None:
    """"Against the triggering enemy" is a gate on the attack context,
    which carries `attacker` -- unlike the damage context, which does
    not. Gating defences this way is the one place the engine is rich."""
    foe = c.trigger.target

    def theirs(ctx: dict[str, Any]) -> bool:
        return ctx.get("attacker") == foe

    c.shift(max(1, c.speed_of() // 2))
    c.bonus(AC, 2, on=c.me, until=When.EONT, kind="power", when=theirs)
    c.bonus(REF, 2, on=c.me, until=When.EONT, kind="power", when=theirs)


_swap("f3212", "f3212b", Swap(3, Usage.ENCOUNTER))


@power("f3212b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("m5495a1"),
       requires_text="wielding the weapon this chain names")
def f3212b(c: Cast) -> None:
    """Both attacks are against the same creature, off-hand first, and
    the advantage the first one grants is laid before the second is
    rolled -- which is the whole point of the printed order."""
    foe = c.target
    if foe is None:
        return
    if c.strike(hand="off"):
        c.damage(c.w(1, hand="off"), c.str_mod)
        c.grants_advantage(on=foe, until=When.EOT)
    if c.strike(on=foe):
        c.damage(c.w(), c.str_mod, on=foe)
    c.shift(max(1, c.speed_of() // 2))


_swap("f3213", "f3213b", Swap(9, Usage.DAILY))


@power("f3213b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.RELIABLE, Keyword.WEAPON],
       attack=Attack(STR, vs=AC), requires=_wielding("m5495a1"),
       requires_text="wielding the weapon this chain names")
def f3213b(c: Cast) -> None:
    """"Slide 3 squares to a square adjacent to you" is a pull: a slide
    picks its own destination and a pull is the one that comes to you."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.pull(3)
        c.prone()
        c.grant_row("f3213c", on=c.me, until=When.EONT)


@power("f3213c", level=1, cls="", usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.RELIABLE, Keyword.WEAPON],
       attack=Attack(STR, vs=AC), requires=_wielding("m5495a1"),
       requires_text="wielding the weapon this chain names",
       trigger="the target stands up",
       on=Trigger(ConditionEnded, lambda w, me, ev: (
           ev.condition == Condition.PRONE
           and team(w, ev.target) != team(w, me)
           and distance_between(w, me, ev.target) <= 1
       ), "an adjacent enemy stands up"))
def f3213c(c: Cast) -> None:
    """Standing up is a prone condition ending, which is the only event
    that announces it. "Cannot stand up (save ends)" pins the condition
    back on rather than applying a new one."""
    foe = c.trigger.target
    if c.strike(on=foe, hand="off"):
        c.damage(c.w(1, hand="off"), on=foe)
        c.prone(on=foe, held=When.SAVE_ENDS)


@power("f3214", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3214(c: Cast) -> None:
    """Both printed choices, made at arm time.

    **The skill half is written.** It was dropped for want of a list of
    skills to offer and there is one: `engine.skills.SKILLS` is seventeen
    entries, and `f3312` in this file already chooses from it. Re-making a
    build-time choice at the start of every fight is the approximation the
    defence half has carried since it was written, so the two halves now
    carry the same one rather than one of them being absent."""
    from combat_engine.engine.skills import SKILLS

    pick = c.choose([FORT, REF, WILL], "which defence")
    if pick is not None:
        c.bonus(pick, 1, on=c.me, until=When.ENCOUNTER, kind="racial")
    skill = c.choose(sorted(SKILLS), "which skill")
    if skill is not None:
        c.bonus(f"skill:{skill}", 2, on=c.me, until=When.ENCOUNTER,
                kind="racial")


@power("f3215", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an adjacent enemy takes damage from your quarry rider",
       on=Trigger(DamageApplied, lambda w, me, ev: (
           ev.source == me
           and getattr(ev, "detail", "") == "cf:ranger-f1"
           and distance_between(w, me, ev.target) <= 1
       ), "your quarry rider damages an adjacent enemy"))
def f3215(c: Cast) -> None:
    """**The quarry rider is identifiable after all.**

    `features/strikers.py:109` pays it with
    `c.damage(..., detail=label)` and the ranger's label is
    `cf:ranger-f1`, so `DamageApplied.detail` names the rider
    exactly. I marked this `c.on_extra_damage()` and wrote the trigger
    as every blow landed on an adjacent quarry -- which the docstring
    admitted fired more often than printed, and which was the wrong
    trade: an approximation that plays is worse than a marker, because
    nothing ever comes back to it.

    The general group is still real but it is not one group, and it is
    smaller than the fifteen rows this note used to claim: seven as of
    2026-10-15, split three ways. Four `p8278` feats read a rider's
    *amount* and cannot, because `p8278` lays a `c.bonus("damage", ...)`
    folded into somebody else's roll rather than a `c.damage` call with a
    `detail` -- which is exactly why they are not this. One changes who a
    rider pays out to. Two raise an ongoing amount, and their dice are
    countable through `c.dice_for`. #619.

    This row only needed the moment, and the moment is announced.

    The 3-at-11th and 4-at-21st steps are paragon and epic; the project
    stops at 10, so the heroic 2 is the whole number."""
    struck = c.trigger.target
    if not c.is_quarry(struck):
        return
    others = [e for e in c.within(1, side="enemy") if e != struck]
    if others:
        c.flat(2, on=others[0])


@power("f3216", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3216(c: Cast) -> None:
    """`dtype=` because the rider's type differs from the weapon damage
    p11749's own line rolls, so the two points meet a poison resistance on
    their own terms. `power` on the damage side is the ref of whatever
    rolled the blow, which is the row's own.

    The miss half is a flat hit and not a `c.damage` roll: the card prints a
    number."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER,
            dtype=DamageType.POISON,
            when=lambda ctx: ctx.get("power") == "p11749")

    def spat(ev: Miss) -> None:
        if ev.attacker == c.me and ev.power == "p11749":
            c.flat(7, dtype=DamageType.POISON, on=ev.target)

    c.watch(Miss, spat, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} spat")


@power("f3217", level=1, cls="", usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=SELF)
def f3217(c: Cast) -> None:
    """Trades a named power's use for temporary hit points.
    `c.expend_row` is the trade: it spends p11738 without casting it and
    returns False once there is nothing left, so the once-a-fight limit
    is that row's and this one is the free action the card prints.

    "You don't gain the normal effect" is what expending rather than
    using means -- p11738's body never runs."""
    if c.expend_row("p11738"):
        c.temp_hp(5 + c.con_mod, on=c.me)


_F3218 = ("p2620", "p10591", "p315", "p10734")


@power("f3218", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3218(c: Cast) -> None:
    """**The Associated Powers line is in the spec now**, so the rider
    has refs to watch and the row is finished. The docstring here used to
    blame `etl/feat._benefit` for breaking at an errata heading and
    eating the list; whatever the cause was, it is fixed, and the marker
    outlived it.

    "Adjacent to that enemy" is measured from the enemy and not from the
    caster, so it is `distance_between` rather than `c.adjacent`, which
    always asks about `c.me`. A plain "+1 bonus" with no type word is
    untyped."""
    c.bonus("skill:perception", 1, on=c.me, until=When.ENCOUNTER,
            kind="feat")

    def screen(ev: Any) -> None:
        near = [a for a in c.allies()
                if distance_between(c.world, a, ev.target) <= 1]
        if not near:
            return
        friend = c.choose(near, "who gains the bonus")
        if friend is not None:
            c.bonus(AC, 1, on=friend, until=When.SONT)

    _on_hit_with(c, _F3218, screen)


@power("f3220", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3220(c: Cast) -> None:
    """The poison save is exact -- the keywords of the row that laid the
    hold, with the burn's type as the fallback.

    **The unbloodied gate is writable after all.** `c.resist_forced`
    takes no `when=`, but it is two lines long and the second of them is
    `self.bonus("forced", ...)`; `movement.py` reads that key with a
    context, so a gated bonus written out is the same modifier with the
    gate the verb does not expose. The gate ignores the context and asks
    the board, which is what "while you are not bloodied" means -- the
    answer changes mid-fight and a modifier laid once would not notice.
    `c.resist_forced(when=)` is still worth having; the row no longer
    waits for it."""
    me = c.me
    c.bonus(
        "save", 2, on=me, until=When.ENCOUNTER, kind="racial",
        when=lambda ctx: Keyword.POISON in ctx.get("keywords", ())
        or ctx.get("dtype") is DamageType.POISON,
    )
    c.bonus("forced", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: not c.bloodied(on=me))


@power("f3221", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit against an enemy",
       on=Trigger(Hit, _i_crit, "you score a critical hit"))
def f3221(c: Cast) -> None:
    """`Hit` carries `critical` as a field, so the crit is asked of the
    event rather than of `c.crit`, which is about the caster's own roll
    and is already over by the time a watcher runs."""
    c.grants_advantage(on=c.trigger.target, to=c.me, until=When.EONT)


_swap("f3222", "f3222b", Swap(6, utility=True))


@power("f3222b", level=1, cls="", usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=MARTIAL,
       requires=_wielding("lotulis"),
       requires_text="wielding the weapon this chain names",
       trigger="you are hit by a melee or a ranged attack",
       on=Trigger(Hit, lambda w, me, ev: ev.target == me,
                  "you are hit by an attack"))
def f3222b(c: Cast) -> None:
    """The bonus is the printed effect; whether raising a defence during
    the interrupt window turns the blow into a miss is the engine's
    business, not the row's."""
    c.bonus(AC, c.wis_mod, on=c.me, until=When.EOT)
    c.bonus(REF, c.wis_mod, on=c.me, until=When.EOT)


_swap("f3223", "f3223b", Swap(3, Usage.ENCOUNTER))


@power("f3223b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("lotulis"),
       requires_text="wielding the weapon this chain names")
def f3223b(c: Cast) -> None:
    """"Strength or Dexterity" is one line with two abilities: the header
    names one and the roll carries the difference as `plus=`, which is
    how the rest of the tree writes it.

    Forgoing the secondary attack to slide 5 instead is offered as the
    choice it is printed as."""
    best = _best_of_two(c)
    others = [e for e in c.within(1, side="enemy") if e != c.target]
    second = others[0] if others else None
    forgo = second is None or not c.may("make the second attack")
    if c.strike(plus=best - c.attack_mod):
        c.damage(c.w(2), best)
        c.slide(5 if forgo else 1)
    c.shift(1)
    if second is None or forgo:
        return
    if c.strike(on=second, plus=best - c.attack_mod, hand="off"):
        c.damage(c.w(2, hand="off"), best, on=second)
        c.slide(1, on=second)


_swap("f3224", "f3224b", Swap(9, Usage.DAILY))


@power("f3224b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=EACH_ENEMY, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("lotulis"),
       requires_text="wielding the weapon this chain names")
def f3224b(c: Cast) -> None:
    """"You can move through enemies' spaces" is rendered as phasing for
    the length of the shift; nothing narrower exists, and phasing also
    waives walls, which no square of a close burst 1 shift will reach."""
    best = _best_of_two(c)
    if c.strike(plus=best - c.attack_mod):
        c.damage(c.w(2), best)
    else:
        c.half_damage(c.w(2), best)
    if c.last:
        c.phasing(until=When.EOT, on=c.me)
        c.shift(max(1, c.speed_of() // 2))


@power("f3225", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3225(c: Cast) -> None:
    """`c.deals` is an override of every weapon blow the creature lands and
    the printed choice speaks for one power, so the hold is laid on
    p12258's own announcement and taken off again on its resolution -- the
    pair brackets the body and nothing else of the turn.

    "You can choose" declines, and declining leaves the thunder alone."""
    held: list[Any] = []

    def picked(ev: PowerUsed) -> None:
        if ev.actor != c.me or ev.power != "p12258":
            return
        word = c.choose(
            [DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING], optional=True
        )
        if word is not None:
            held.append(c.deals(word, on=c.me, until=When.EOT))

    def done(ev: PowerResolved) -> None:
        if ev.actor != c.me or ev.power != "p12258":
            return
        while held:
            c.end_effect(held.pop(), on=c.me)

    c.watch(PowerUsed, picked, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} pick")
    c.watch(PowerResolved, done, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} drop")


@power("f3226", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3226(c: Cast) -> None:
    """Same subject as f3204 and read the same way. "The end of his or her
    next turn" is the ally's own clock. No type word is printed in front of
    "bonus", so it is untyped."""

    def paid(ev: PowerResolved) -> None:
        if ev.actor != c.me or ev.power != "p12244":
            return
        who = _who_rolled(ev.trigger)
        if who is None or who not in c.allies():
            return
        c.bonus(AC, 2, on=who, until=When.EOTNT)
        c.bonus(WILL, 2, on=who, until=When.EOTNT)

    c.watch(PowerResolved, paid, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} guard")


@power("f3227", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3227(c: Cast) -> None:
    """Raises the curse rider by a die, and types only the new die.

    **Written off `DamageApplied.detail`.** `features/strikers.py`'s
    `extra_damage` pays the rider with `detail="cf:warlock-f4"`, so the
    moment it lands is readable and names the creature it landed on. The
    rider's own once-a-round latch is upstream of that, so this cannot pay
    twice in a window the rider paid once.

    `c.change_dice("cf:warlock-f4", "2d6")` was the other candidate -- it
    is the door four other feats use to raise a striker's dice -- and it is
    wrong here: one roll takes one type, and the card types the increase
    only. Two blows, the printed 1d6 untyped and this 1d6 psychic, is what
    "this additional damage is psychic" says, and it is also the only
    reading under which a psychic resistance gets to halve the right half."""
    def psychic(ev: DamageApplied) -> None:
        if ev.source != c.me or ev.detail != "cf:warlock-f4":
            return
        c.damage("1d6", dtype=DamageType.PSYCHIC, on=ev.target, detail=c.ref)

    c.watch(DamageApplied, psychic, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} psychic")


@power("f3228", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3228(c: Cast) -> None:
    """One more healing surge, and an Endurance check rolled twice.

    **Both halves written.** `Health.max_surges` is a plain field that
    `feats/paladin.py` already raises from content, which is
    `_one_more_surge` above. And an Endurance check is not out of combat:
    `skills.check` announces a `SkillCheck` *before* totalling, reads
    `natural` back afterwards, and `powers/ranger/level_6.py` answers that
    very check. So "roll twice" is a second d20 laid in `Window.BEFORE` --
    the window matters, because the resolve callback runs between the two.

    "Use either result" is taken as the better of the two: a headless run
    has to answer, and nobody prints this meaning to roll worse."""
    _one_more_surge(c)

    def twice(ev: SkillCheck) -> None:
        if ev.actor != c.me or ev.skill != "endurance":
            return
        ev.natural = max(ev.natural, c.roll("1d20"))

    c.watch(SkillCheck, twice, on=c.me, until=When.ENCOUNTER,
            window=Window.BEFORE, label=f"{c.ref} endurance")


_F3230 = ("p4541", "p971", "p10592", "p997")


@power("f3230", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3230(c: Cast) -> None:
    """**The spec carries the Associated Powers line now**, same as
    `f3218`, so the once-per-encounter advantage has somewhere to hang.

    The printed limit is the `once=` on the watch and not a `usage`: a
    triggered trait declared ENCOUNTER spends a use on every firing
    (#210), and `c.watch(once=True)` spends the hold only when the
    handler actually did something."""
    c.bonus("skill:endurance", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def opening(ev: Any) -> None:
        c.grants_advantage(on=ev.target, to=c.me, until=When.EONT, once=True)

    _on_hit_with(c, _F3230, opening, once=True)


@power("f3231", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3231(c: Cast) -> None:
    """"Replace the effect" has nothing to take away first: p12258's mark
    hangs off its hit and its attack line is the half that waits, so the
    save-ends mark laid here is the only one on the target. When that line
    lands, both are the same relation from the same source and the longer
    one is what stands.

    "An attack that does not include you" is the whole set one use was
    aimed at, which rides on the roll as `among`; `ev.target` alone is
    false for a burst that caught the caster too."""

    def landed(ev: Hit) -> None:
        foe = ev.target
        c.mark(on=foe, until=When.SAVE_ENDS)

        def spurned(shot: AttackRolled) -> None:
            if shot.attacker != foe or not c.marked(on=foe, by=c.me):
                return
            if c.me not in getattr(shot, "among", (shot.target,)):
                c.flat(5, dtype=DamageType.THUNDER, on=foe)

        c.watch(AttackRolled, spurned, on=c.me, until=When.ENCOUNTER,
                label=f"{c.ref} spurned")

    _on_hit_with(c, ("p12258",), landed)


@power("f3232", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3232(c: Cast) -> None:
    """Swaps one pact boon's payout for a power point.

    **Written, and the three things that were in the way are all gone.**
    The old note was right that this needed the word *instead* and wrong
    about why the rest could not be said:

    * the charge is no longer the boon row's encounter use, which arming
      spent before round 1 -- it is `features.warlock.FELL`, a
      `c.spend_charge` key (#529);
    * `c.regain_points()` exists now. The old note reached for
      `c.transfer_points`, which **refuses self-targeting** and returns 0
      for `who == self.me`, so there was genuinely nothing to write;
    * `cf:warlock-f1s4` now offers its regain as the named clause
      `BOON_REGAIN` through `c.instead_of_now`, so this can replace it from
      outside.

    The old worry about two handlers racing on one `Dropped` is answered by
    the shape rather than by ordering: this row does not watch `Dropped` at
    all. It registers a substitution once, and the boon's own watcher runs
    it *in place of* handing the charge back -- so there is exactly one
    handler and no arming order to depend on.

    A trait, so this is registered once at the start of the fight and the
    trade is settled for the whole encounter, which is what the card says.
    """
    c.pre_empt("cf:warlock-f1s4", BOON_REGAIN,
               lambda using: using.regain_points(1))


@power("f3233", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3233(c: Cast) -> None:
    """"Any character" is the caster as well as the allies -- p11778's other
    option moves only the caster -- so the shift is read off whoever moved
    and not off a side. Plain "+2 bonus" with no type word, so untyped."""
    during = _resolving(c, "p11778")

    def stepped(ev: MoveEnd) -> None:
        if not during() or ev.kind_ != "shift":
            return
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, 2, on=ev.actor, until=When.EONT)

    c.watch(MoveEnd, stepped, on=c.me, until=When.ENCOUNTER, label=f"{c.ref} step")


#: p704 is gone from this list because its clause is written into p704's
#: own body (#550). The watcher still covers the other three.
_F3234 = ("p917", "p10890", "p10472")


@power("f3234", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3234(c: Cast) -> None:
    """The plainest of the seven: a skill bonus and a push."""
    c.bonus("skill:athletics", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def shove(ev: Any) -> None:
        c.push(1, on=ev.target)

    _on_hit_with(c, _F3234, shove)


@power("f3235", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3235(c: Cast) -> None:
    """A free saving throw when the pact boon comes back.

    **Written: the charge was held all along.** `cf:warlock-f1s4` is
    `action=NONE` with `usage=ENCOUNTER`, so arming it spends its one use
    and the boon's own `Dropped` watch hands that use back when a cursed
    enemy falls -- which is the moment this row wants.

    It is read rather than hooked, because `c.restore_use` announces only a
    `Note`. Two guards, and **both** are load-bearing -- driven on a board,
    because the spent use alone looked like enough and is not:

    * the pact, because `chargen` deals every warlock all seven legs and
      `turns.arm_traits_of` arms all of them, so `cf:warlock-f1s4`'s one use
      is spent at the start of every warlock's fight whatever pact it took.
      Only this one's body gets past its own `c.build` to register the
      regain, so without the same word here an infernal warlock saved on
      every cursed kill;
    * the use being spent, which is what makes this the *regain* and not
      just a kill, and what stops a second cursed kill paying a second save
      -- the restore would find nothing to give back either.

    `Window.BEFORE`, so the read happens before the boon's own watch clears
    the count. On the audit board the character is another pact, so the row
    reports silent there and was checked by hand with the leg armed."""
    if not c.build("sorcerer-king"):
        return

    def regained(ev: Dropped) -> None:
        if not cursed_by_me(c.world, c.me, ev):
            return
        if "cf:warlock-f1s4" not in c.expended(on=c.me):
            return
        c.save(on=c.me)

    c.watch(Dropped, regained, on=c.me, until=When.ENCOUNTER,
            window=Window.BEFORE, label=f"{c.ref} boon save")


@power("f3237", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=PROSE)
def f3237(c: Cast) -> None:
    """Pays out when a daily is used *without* a named ability, and the
    beneficiary is picked by standing next to a familiar.

    **Re-aimed off `c.class_feature()`**, the same ability as `f3190`
    and `f3244` and the same finding: nothing in the compendium is that
    row, so there is nothing to give it a ref.

    **One marker now, not two.** "The familiar's position is the second
    absence" was true when written and is not: `c.familiar` answers, and a
    familiar in active mode holds a square -- `c.familiar_mode` places it
    and only the passive one is off the grid. So adjacency to it is an
    ordinary read, and what is left is the defiling half alone. #620."""


@power("f3239", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3239(c: Cast) -> None:
    """`"save"` is the key `c.save` reads, and `c.penalty` takes no
    `kind`."""
    _on_hit_with(
        c, ("p11749",),
        lambda ev: c.penalty("save", 2, on=ev.target, until=When.EONT),
    )


@power("f3240", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you take damage from an attack",
       on=Trigger(DamageApplied, targets_me, "you take damage"))
def f3240(c: Cast) -> None:
    """The printed gate is "while you are affected by <a named row of
    yours>", and that is `c.world.effects.of`: it lists the holds standing
    on the creature, and an effect's label starts with the ref of the row
    that laid it. Asked here, in the body, which is the moment the damage
    lands -- a `requires=` would be asked when the trait is armed, before
    the racial power has been used at all.

    `c.bonus(dice=)` is the extra die: a flat `c.damage` here would be a
    second blow rather than a rider on the next one."""
    if not any(
        not eff.ended and eff.label.split()[:1] == ["p6188"]
        for eff in c.world.effects.of(c.me)
    ):
        return
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EONT, once=True,
            when=lambda ctx: _melee(ctx.get("power", "")))


@power("f3242", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3242(c: Cast) -> None:
    """The daze is the whole benefit; p12315 already slows on the same hit
    and the two hold separately."""
    _on_hit_with(
        c, ("p12315",), lambda ev: c.dazed(on=ev.target, until=When.EONT)
    )


@power("f3243", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3243(c: Cast) -> None:
    """"You can slide the target 3 squares" names no destination, so the
    decider picks it."""
    _on_hit_with(c, ("p12315",), lambda ev: c.slide(3, on=ev.target))


@power("f3244", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3244(c: Cast) -> None:
    """A defence penalty that rides on a named ability used with a daily.

    **Re-aimed off `c.class_feature()`** -- see `f3190`. Same ability,
    same prerequisite term, and it is not a class feature."""


_F3245 = ("p2099", "p2248", "p10592", "p4542")


@power("f3245", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3245(c: Cast) -> None:
    """"The next saving throw you make" is `once=True`: without it the
    bonus is paid on every save until the duration lapses."""
    c.bonus("skill:heal", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def steady(ev: Any) -> None:
        c.bonus("save", 2, on=c.me, until=When.SONT, once=True)

    _on_hit_with(c, _F3245, steady)


_F3246 = ("p10470", "p1505", "p653", "p1063")


@power("f3246", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3246(c: Cast) -> None:
    """The Stealth bonus, and 3 extra damage on the *next* blow to land on
    whoever this hit.

    **No vulnerability is involved and the old marker was aiming at the
    wrong mechanism.** `c.vulnerable` has no one-shot form, so every hit
    inside the window was paid; written as a `DamageRolled` watcher with
    `once=True` it is spent by the first blow and nothing else. The amount
    on that event is mutable and `resolve.deal_damage` reads it back, and
    rewriting a field is what `c.watch`'s `once=` counts as doing
    something (#540), so the hold retires itself.

    **Any attacker, which is the printed word.** "The next attack that
    hits that enemy" names nobody, so the watcher is keyed on the victim
    rather than on me -- an ally landing the next blow collects it. The
    hold sits on the foe and clocks on *my* next turn end, because
    `When.EONT` is the source's turn and `c.watch` passes the caster as
    source."""
    c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def soft(ev: Any) -> None:
        foe = ev.target

        def extra(blow: Any) -> None:
            if blow.target == foe:
                blow.amount += 3

        c.watch(DamageRolled, extra, on=foe, until=When.EONT, once=True,
                label=f"{c.ref} soft spot")

    _on_hit_with(c, _F3246, soft)


@power("f3247", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3247(c: Cast) -> None:
    """Three powers named by their category and not by ref.

    **Written.** The category is an ordinary `cls` value and all ten rows
    that carry it are declared, so the set is `_wild_talents` above -- the
    same registry read `items/misc.py` makes for an arcane class's attack
    rows. Nothing had to be imported and nothing had to be enumerated that
    was not already enumerable.

    Picked one at a time and taken out of the pool, so three choices are
    three different rows rather than one row three times."""
    pool = _wild_talents()
    for _ in range(3):
        pick = c.choose(pool, "which wild talent")
        if pick is None:
            break
        pool.remove(pick)
        c.grant_row(pick, on=c.me, until=When.ENCOUNTER)


@power("f3248", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit",
       on=Trigger(Hit, _i_crit, "you score a critical hit"))
def f3248(c: Cast) -> None:
    """"Your primary ability modifier" is now `c.primary_mod`, which reads
    the build rather than the sheet.

    It had been standing in with the largest modifier, which is the same
    number for most builds and generous for the ones whose best score is
    not what they attack with -- a battle cleric with Strength above
    Wisdom paid out the wrong one. The marker on this row named
    `c.attack_ability()`, which was the wrong gap: nothing here swaps an
    ability, it only needed to be told which one the class uses.
    """
    mod = c.primary_mod
    if mod <= 0:
        return
    c.temp_hp(mod, on=c.me)
    for friend in c.within(1, side="team"):
        c.temp_hp(mod, on=friend)


_F3249 = ("p2104", "p4369", "p620")


@power("f3249", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.grant_action(toward=)",))
def f3249(c: Cast) -> None:
    """**The spec carries the Associated Powers line now**, same as
    `f3218` and `f3230`, so the shift has something to ride on.

    "Larger than you" is `.order` and not `.squares`: Tiny, Small and
    Medium all occupy one square, so a footprint comparison cannot tell
    them apart. `c.grant_action` follows `c.target`, so the offer is
    aimed at `c.me` by hand.

    Dropped, and **not** the same gap `f3206b` had: that row calls
    `c.shift` itself and now names the creature to close on. Here the
    shift is taken later, by whoever the minor action was granted to, and
    `c.grant_action` carries a cost and a count and nothing about where
    the step may end -- so "to a square adjacent to the enemy" has no
    channel to travel down, whatever `c.shift` learns to take."""
    c.bonus("skill:acrobatics", 2, on=c.me, until=When.ENCOUNTER,
            kind="feat")

    def close(ev: Any) -> None:
        if c.size_of(on=ev.target).order <= c.size_of(on=c.me).order:
            return
        c.grant_action("shift", MINOR, on=c.me, until=When.EOT)

    _on_hit_with(c, _F3249, close)


# -- the psionic tail: power points, spent one at a time --------------------


@power("f3274", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3274(c: Cast) -> None:
    """One more healing surge, and one skill standing in for another.

    **Both halves written, and the second is simpler than the arithmetic
    it was marked for.** `skills.check` totals the modifier *inside* its
    resolve callback and reads the skill off the event, so rewriting
    `ev.skill` in the interrupt window **is** making the other check:
    ability, half level, every standing modifier and the armour penalty all
    follow the new name. Laying the difference of the two modifiers as a
    bonus -- which is what `c.lend_skills` would have been -- would have had
    to subtract one skill's own modifiers and add the other's by hand.

    "While you are not bloodied" is asked at the roll and not at arm time,
    because it changes mid-fight; the surge half is `_one_more_surge`, as
    `f3228`."""
    _one_more_surge(c)

    def instead(ev: SkillCheck) -> None:
        if ev.actor != c.me or ev.skill != "endurance":
            return
        if c.bloodied(c.me) or not c.may("use arcana instead", who=c.me):
            return
        ev.skill = "arcana"

    c.watch(SkillCheck, instead, on=c.me, until=When.ENCOUNTER,
            window=Window.BEFORE, label=f"{c.ref} arcana")


@power("f3276", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you daze or stun an enemy with a psionic power",
       on=Trigger(ConditionApplied, lambda w, me, ev: (
           ev.source == me
           and ev.condition in (Condition.DAZED, Condition.STUNNED)
           and team(w, ev.target) != team(w, me)
       ), "you daze or stun an enemy"),
       dropped=("ConditionApplied.power",))
def f3276(c: Cast) -> None:
    """`ConditionApplied` says who, what and for how long and never which
    row did it, so "using a psionic power" cannot be checked -- the slide
    is offered whatever dazed the enemy."""
    if _point(c):
        c.slide(1, on=c.trigger.target)


@power("f3292", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.recast(usage=)", "Target.square"))
def f3292(c: Cast) -> None:
    """Turns an encounter cantrip into an at-will -- `c.recast` changes
    what a row costs, not how often it may be used -- and then hangs
    combat advantage off an enemy standing beside the *object or square*
    the cantrip was aimed at. `Target` has sides for creatures and for an
    object and none for a square, so there is no aim point to stand beside:
    `Target.square` is the gap, and p1217 declares `NO_TARGET` because of
    it."""


@power("f3295", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3295(c: Cast) -> None:
    """A point back when an action point buys an extra attack.

    **Written against the component.** `PowerPoints.points` is a plain
    field and `c.transfer_points` already adds to one with
    `theirs.points += gone`, so handing a point back needs no new verb. The
    pool's own maximum is the cap, because a point cannot be regained that
    was never spent.

    Two watches rather than one, because the card does not pay for the
    point -- it pays for the *attack* the point buys.
    `ActionPointSpent` says the point went and the first attack declared in
    that same round is the extra one. The round is the window: an action
    point buys an action for the turn it is spent in, so a flag left
    standing would pay for an ordinary swing a round later."""
    bought: dict[str, int] = {}

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor == c.me:
            bought["round"] = c.world.round

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker != c.me or bought.pop("round", None) != c.world.round:
            return
        pool = c.world.get(c.me, PowerPoints)
        if pool is None:
            return
        pool.points = min(pool.maximum, pool.points + 1)

    c.watch(ActionPointSpent, spent, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} point")
    c.watch(AttackDeclared, swung, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} swing")


@power("f3297", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with your racial breath attack",
       on=Trigger(Hit, _hit_with("p1448"), "you hit with p1448"))
def f3297(c: Cast) -> None:
    """The row is named by ref, so the watcher is exact."""
    c.vulnerable(5, DamageType.PSYCHIC, on=c.trigger.target, until=When.EOT)


@power("f3308", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.run()",))
def f3308(c: Cast) -> None:
    """The point-spend half is writable because `ActionSpent` names the
    cost: a move action is announced and the bonus is laid inside the
    turn it belongs to. Running is not an action this engine has, so the
    standing +1 on a run or a charge is the dropped half."""

    def hustle(ev: Any) -> None:
        if ev.actor != c.me or ev.cost != ActionType.MOVE:
            return
        if _point(c):
            c.bonus("speed", 2, on=c.me, until=When.EOT)

    c.watch(ActionSpent, hustle, on=c.me, until=When.ENCOUNTER)


@power("f3309", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make a saving throw",
       on=Trigger(SavingThrow, about_me, "you make a saving throw"))
def f3309(c: Cast) -> None:
    """+1 to saving throws while you hold a power point, and +3 until the end
    of your turn if you spend one as the save is rolled.

    "While you have at least 1 power point" is a gate that reads the pool at
    the moment the save is rolled, which is what a `when=` does -- the pool
    empties mid-fight and a bonus laid once would not notice.

    **The second clause is written now.** Its note said `SavingThrow`
    "carries `bonus` but only `saved` is read back", and that was already
    untrue -- `c.reroll_save` has written to `ev.bonus` and recomputed
    `ev.saved` for as long as it has existed. `c.boost_roll` (#495) is the
    verb for adding to a roll already down, and it does both halves.

    The standing bonus is raised to +3 for the rest of the turn as well as
    the roll in hand, because the card says "until the end of your turn" and
    a second save this turn gets the better number. The +1 effect is left
    alone and a +2 laid beside it: both are feat bonuses and so do not
    stack, but `c.bonus` buckets by type and takes the larger, which is the
    printed +3 rather than +4. #495.
    """
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: c.points() > 0)
    if c.points() < 1 or not c.spend_points(1):
        return
    c.boost_roll(2, kind="save")
    c.bonus("save", 3, on=c.me, until=When.EOT, kind="feat")


@power("f3310", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3310(c: Cast) -> None:
    """Both halves land because a trait arms at the top of the fight,
    which is when initiative is rolled -- so the point is offered before
    the number is wanted, and `c.initiative` moves the creature in the
    order once."""
    c.initiative(6 if _point(c) else 3, on=c.me)


@power("f3311", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3311(c: Cast) -> None:
    """"A +1 bonus to opportunity attack rolls. When you make an
    opportunity attack, you can spend 1 power point to gain a +2 power
    bonus to the attack roll."

    The standing +1 is a plain gated bonus -- the attack context carries
    `opportunity`.

    **The +2 is a watch, not a declared trigger.** This row already lays a
    standing modifier, and a row holds one or the other: with an `on=` the
    body would run only when the trigger fired and the +1 would never be
    laid at all. So the trait arms its own listener.

    `c.boost_roll` is what the old note said did not exist -- it adds to a
    roll already down and recomputes the outcome from the untouched
    natural. The point is spent **first** and the boost is abandoned if the
    pool is empty, because the card sells the bonus for the point.
    """
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("opportunity")))

    def bought(ev: Any) -> None:
        if ev.attacker != c.me or not getattr(ev, "opportunity", False):
            return
        if c.may("spend a power point") and c.spend_points(1):
            # **`c.trigger` bound across the call, and the point was being
            # spent for nothing without it.** `c.boost_roll` reads the roll
            # off `self.trigger`, which the dispatcher sets only for a row
            # declared with `on=` -- and this row deliberately has none, so
            # that it can also lay the standing modifier above. A watcher
            # is handed the event and does not rebind the field, so
            # `boost_roll` found None and returned False **after**
            # `c.spend_points(1)` had already taken the point.
            #
            # Unmarked, so the row reported finished the whole time.
            # `f3312` below has the same shape and was written with the
            # bind from the start; this is that fix applied here.
            was, c.trigger = c.trigger, ev
            try:
                c.boost_roll(2, kind="attack")
            finally:
                c.trigger = was

    c.watch(AttackRolled, bought, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} bought")


@power("f3312", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3312(c: Cast) -> None:
    """**Re-aimed off `c.bonus('skill:any')`, which was never the hold.**
    `c.bonus` wants a named skill and there is a list of them --
    `engine.skills.SKILLS`, seventeen entries, which `items/misc.py`
    already offers this way. So the standing +2 plays, chosen at arm
    time the way `f3214` chooses its defence.

    **The point-for-a-bonus half plays now, and the old note was wrong
    about the window.** `SkillCheck` is a `Decision` announced before its
    modifiers are totalled -- its own docstring says so -- and
    `c.boost_check` adds to a roll already down, reading the result back
    out of the event. So the moment is announced and does not need
    anything new.

    **A watch rather than a declared trigger**, for the reason `f3311`
    beside it gives: the row also lays a standing modifier, and with an
    `on=` the body would only ever run when the trigger fired, so the +2
    would never be laid at all.

    `c.trigger` is bound across the call and put back. `boost_check`
    reads the event off the `Cast`, and a watcher does not rebind it --
    the save-and-restore idiom `powers/cleric/level_1_b.py` uses. Without
    it the verb returns False and the point is paid for nothing.

    The point is spent **first** and the boost abandoned if the pool is
    empty, again as `f3311` does: the card sells the bonus for the point.
    What lands is a bare number on a settled roll, so the printed
    **power** type has nowhere to live -- there is no modifier bucket
    left once the die is down -- which is the same limit every
    `boost_check` row in the tree carries."""
    from combat_engine.engine.skills import SKILLS

    pick = c.choose(sorted(SKILLS), "which skill")
    if pick is None:
        return
    c.bonus(f"skill:{pick}", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def bought(ev: Any) -> None:
        if ev.actor != c.me or ev.skill != pick:
            return
        if c.may("spend a power point") and c.spend_points(1):
            was, c.trigger = c.trigger, ev
            try:
                c.boost_check(3)
            finally:
                c.trigger = was

    c.watch(SkillCheck, bought, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} bought")


@power("f3313", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.max_hp()",),
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3313(c: Cast) -> None:
    """Heroic tier, so 5. The hit points per tier are dropped -- nothing
    raises a character's maximum."""
    if c.points() >= 1 and c.may("spend a power point", who=c.me):
        c.spend_points(1)
        c.heal(5, on=c.me)


@power("f3317", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.telepathy()",))
def f3317(c: Cast) -> None:
    """The ally is chosen from within the radius of a telepathy the
    character has, and nothing records a telepathy range -- "one ally
    you can see" would be a different and much larger feat."""


@power("f3323", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_points_spent()",))
def f3323(c: Cast) -> None:
    """Fires the first time the pool empties. `c.restore_use` is the verb
    waiting for it; nothing announces a pool reaching zero."""


@power("f3329", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your racial will power",
       on=(
           Trigger(PowerUsed, _my_use("p2475"), "you use p2475"),
           Trigger(
               ConditionApplied,
               lambda w, me, ev: (
                   ev.target == me and ev.condition is Condition.SURPRISED
               ),
               "you are surprised",
           ),
       ))
def f3329(c: Cast) -> None:
    """Two printed clauses and two declared triggers -- `on=` takes a
    sequence, and declaring one of the two would have looked finished.

    The shift answers the use of p2475. The second clause spends the
    same row **unused**, which is `c.expend_row`: the use goes, p2475's
    own body never runs, and the surprise is shrugged off only if there
    was a use to pay with.

    `ConditionApplied` names its subject `target`, so the predicate is
    written on `ev.target` and not `about_me`."""
    if isinstance(c.trigger, ConditionApplied):
        if c.expend_row("p2475"):
            c.cure(Condition.SURPRISED, on=c.me)
        return
    c.shift(1)


@power("f3389", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("PowerPoints.spent_until_extended_rest",))
def f3389(c: Cast) -> None:
    """The feature is a row, so "you gain it" is `c.grant_row`.

    **Re-aimed off `dsl.use(augment=)`, which arrived.** Spending a point
    to augment is now a thing a character can do, so that half of the
    printed sentence is no longer this row's gap -- and handing over
    `cf:psion-f1` now buys a real feature rather than a refused row.

    **The point itself is written now.** "Nothing adds to a pool" was
    wrong: `PowerPoints.points` is a plain field and `c.transfer_points`
    already writes it, so the grant is that write behind a once-a-fight
    latch, and the pool is made for a character that had none -- which is
    the whole point of a feat that hands out the class feature. `maximum`
    is left alone deliberately: the point sits over the pool's own ceiling,
    exactly as a transferred one does and for the same reason.

    What is left is the printed restriction, and the marker now names it
    rather than the pool write. Once spent this point does not come back
    until an extended rest, and `PowerPoints.refresh` restores the whole
    pool every encounter -- a rule about rests, which is nothing this row
    can call and nothing one encounter can show.

    **Re-pointed off `c.regain_points()`, which arrived and is not this.**
    That verb caps at the pool's maximum, by design: a regain refills what
    was spent. This point sits *over* the ceiling, exactly as a
    transferred one does, so the existing write is the right one and
    swapping it for the new verb would hand the character nothing at all.
    """
    c.grant_row("cf:psion-f1", on=c.me, until=When.ENCOUNTER)
    key = (id(c.world), c.ref, c.me)
    if _POINT_GRANTED.get(key):
        return
    _POINT_GRANTED[key] = True
    pool = c.world.get(c.me, PowerPoints) or c.world.add(c.me, PowerPoints())
    pool.points += 1


@power("f3390", level=1, cls="", usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3390(c: Cast) -> None:
    """"Choose a power granted by <a feature>."

    Re-aimed. The feature has a list now -- its options are declared --
    so the choosing is `c.borrow_row(among=...)` and the handing over is
    `c.grant_row`. What is left is that each option opens with
    `if not c.build("f0sN"): return`, which is the word *one* said where
    a member of the class can read it and is false for everybody
    else."""


@power("f3391", level=1, cls="", usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3391(c: Cast) -> None:
    """Same shape: every power a named feature grants, once a day. The
    three options are declared and each one gates itself on a leg."""


@power("f3392", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       )
def f3392(c: Cast) -> None:
    """One of another class's at-wills, chosen by level rather than by
    ref, which is exactly the set `c.borrow_row` reads off the registry.
    `uses=1` is the printed limit: an at-will handed over bare is an
    extra attack every turn.

    Dropped, and **re-aimed off `c.lend_skills()`**: the training half
    is plain training in a skill from another class's list, which is
    `chargen.skill_training()` and a build-time fact. `c.lend_skills` is
    one skill *standing in for* another -- what `f3274` prints -- and
    naming it here pointed ten rows at the wrong verb."""
    c.borrow_row("monk", level=1, uses=1)


@power("f3393", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3393(c: Cast) -> None:
    """The one row in this family that names its power, so it is an
    ordinary `c.grant_row`. The once-per-encounter limit is the granted
    row's own usage."""
    c.grant_row("p10439", on=c.me, until=When.ENCOUNTER)


@power("f3394", level=1, cls="", usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3394(c: Cast) -> None:
    """A power granted by a named feature, once a day. Same as f3390:
    the four options are declared and each refuses itself off its
    leg."""


@power("f3395", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.telepathy()",))
def f3395(c: Cast) -> None:
    """The card is the combat half and it is handed over. Dropped: the
    telepathy range, which is a fact about the sheet that no verb
    writes."""
    c.set_origin("immortal", until=When.ENCOUNTER)
    c.grant_row("f3395b", on=c.me, until=When.ENCOUNTER)


@power("f3395b", level=1, cls="", usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=PSIONIC,
       trigger="you take damage from an attack",
       on=Trigger(DamageRolled, targets_me, "you take damage"))
def f3395b(c: Cast) -> None:
    """`DamageRolled` is the interrupt window for this: the number exists
    and has not been taken off hit points yet, which is what `c.reduce`
    needs. The 11th- and 21st-level steps are out of scope."""
    c.reduce(c.int_mod)


@power("f3396", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3396(c: Cast) -> None:
    """Same shape as f3395, and this one has no third clause."""
    c.set_origin("aberrant", until=When.ENCOUNTER)
    c.grant_row("f3396b", on=c.me, until=When.ENCOUNTER)


@power("f3396b", level=1, cls="", usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.PSIONIC, Keyword.PSYCHIC],
       trigger="you take damage from an attack",
       on=Trigger(DamageApplied, targets_me, "you take damage"))
def f3396b(c: Cast) -> None:
    """An aura with teeth. `c.burns` pays on entering the aura or
    starting a turn in it; the card says entering or *ending* a turn
    there, which is the same square and one tick earlier."""
    ring = c.aura(1, until=When.EONT)
    if ring:
        c.burns(ring, 5, DamageType.PSYCHIC)


@power("f3397", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use f3395b",
       on=Trigger(PowerUsed, _my_use("f3395b"), "you use f3395b"))
def f3397(c: Cast) -> None:
    """`PowerUsed` announces before the body runs, which is fine here:
    the resistance is not reading anything the body does."""
    if c.int_mod > 0:
        c.resist(c.int_mod, until=When.EONT)


@power("f3402", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("query.immune_to(keyword)",))
def f3402(c: Cast) -> None:
    """The feature is `cf:ardent-f0` and its radius is a column, not a
    guess: `get(...).reach.size` is the burst the row declares, so this
    row cannot drift away from it.

    That feature lays modifiers rather than an aura -- its own docstring
    says it is a snapshot -- so "within the radius" is asked of the board
    at the moment of the critical, which is the live reading and the one
    the sentence means.

    A trait, and `AT_WILL` rather than `ENCOUNTER`: the card prints no
    limit, and a triggered `action=NONE` row declared `ENCOUNTER` spends
    a use every firing (#210). The dropped clause is "not immune to
    fear" -- `query.immune_to` answers for a condition and a keyword
    immunity is not something a creature carries.
    """
    me = c.me
    declared = get("cf:ardent-f0")
    radius = declared.reach.size if declared is not None and declared.reach else 0
    if radius <= 0:
        return

    def crit(ev: Hit) -> None:
        foe = ev.attacker
        if not ev.critical or foe == me:
            return
        if foe not in c.within(radius, side="enemy"):
            return
        c.penalty("attack", 2, on=foe, until=When.EOTNT)
        if c.bloodied(on=me):
            c.push(1, on=foe)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=me, label="f3402")


@power("f3403", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p10440",
       on=Trigger(PowerUsed, _my_use("p10440"), "you use p10440"))
def f3403(c: Cast) -> None:
    """Targets are chosen before the body runs, so `ev.targets` is the
    one thing on `PowerUsed` that is safe to read."""
    for who in c.trigger.targets:
        c.slide(1, on=who)
        c.grants_advantage(on=who, until=When.EONT)


@power("f3404", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3404(c: Cast) -> None:
    """Retypes one named row's damage, and lets that row through
    insubstantial.

    **Written, and not with `c.deals`.** That verb was always the wrong
    door: it recolours everything a creature deals and its label narrows
    only by `Keyword.WEAPON` or `Keyword.IMPLEMENT`, so there is no ref in
    it to aim. `DamageRolled` is the door -- a mutable `dtype` that
    `resolve.deal_damage` reads back off the event after the emit, with its
    own comment saying only the power's own part is retyped -- and `detail`
    on it is the row's ref, so `FLURRIES` is the gate.

    The second clause needed no narrowing verb either: `ignore
    insubstantial` is an ordinary modifier key read off the attacker, and
    `when=` is handed the damage context, which carries `power`. The
    halving happens after the retype, so both clauses speak about the same
    blow.

    "You can" is asked once, at arm time, rather than per blow. Psychic is
    worse against some creatures and the whole point against an
    insubstantial one, and a single answer is what keeps the two clauses
    agreeing with each other -- asked per blow, the standing modifier would
    not know which way the last one went."""
    if not c.may("deal psychic damage with the flurry", who=c.me):
        return

    def recolour(ev: DamageRolled) -> None:
        if ev.source == c.me and ev.detail in FLURRIES:
            ev.dtype = DamageType.PSYCHIC

    c.watch(DamageRolled, recolour, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} psychic")
    c.ignore_resistance(
        insubstantial=True, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") in FLURRIES,
    )


@power("f3405", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with an augmented at-will",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me and any(r.critical for r in ev.rolls)
       ), "you score a critical hit with one of your powers"))
def f3405(c: Cast) -> None:
    """`PowerResolved` rather than `Hit`, because the second branch asks
    whether the target "is dazed by the power" -- a rider the triggering
    attack inflicts, which `Hit` fires too early to see.

    `c.points_spent` is what "augmented" means: the pool records the
    spend against the row's ref."""
    ev = c.trigger
    p = get(ev.power)
    if p is None or p.usage != Usage.AT_WILL:
        return
    if Keyword.PSIONIC not in p.keywords or c.points_spent(ev.power) <= 0:
        return
    for roll in ev.rolls:
        if not roll.critical or not roll.target:
            continue
        if c.is_(Condition.DAZED, roll.target):
            c.flat(5, dtype=DamageType.PSYCHIC, on=roll.target)
        else:
            c.dazed(on=roll.target, until=When.EONT)


# -- the warlock augment family ---------------------------------------------


@power("f3416", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3416(c: Cast) -> None:
    """"Forgo the extra damage the augment would deal to instead grant the
    target vulnerability to all damage equal to your Intelligence modifier
    until the start of your next turn."

    "Vulnerability to **all** damage" is `c.vulnerable`'s default and not a
    damage type: `dtype=None` means "takes `amount` extra from every hit",
    which is the sentence. Written as `DamageType.ALL` first -- a member
    that does not exist, caught by `types.py`.
    """
    c.bonus("skill:diplomacy", 2, on=c.me, until=When.ENCOUNTER,
            kind="feat")

    def soften(using: Cast) -> None:
        foe = using.target
        if foe is not None and using.int_mod > 0:
            using.vulnerable(using.int_mod, on=foe, until=When.SONT)

    c.pre_empt("p12887", "fell_might_damage", soften)


#: "In addition to regaining the use of your fell might, whenever you drop
#: an enemy you have cursed to 0 hit points ...". The regaining is the
#: pact boon and belongs to `cf:warlock-f1s4`; the sentence after it is
#: this row, and `Dropped` plus `cursed_by_me` is exactly that sentence.
_CURSED_FELL = "an enemy under your curse drops to 0 hit points"

#: The heroic half of each card's "Associated Powers" line. Both print four
#: more refs at paragon and epic that this build does not import, so naming
#: those would record refs resolving to nothing -- #281.
_ASSOCIATED = {"f3417": ("p4069", "p4177"), "f3419": ("p1401", "p1462")}


@power("f3417", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger=_CURSED_FELL,
       dropped=AUGMENT)
def f3417(c: Cast) -> None:
    """Two of three clauses written; only the augment is still a gap.

    "Hits with a damaging attack" is `DamageApplied` rather than `Hit`:
    the event names the row that dealt it, so an attack can be told from
    a burn, and it fires only when hit points actually came off.
    `once=True` is "the **next** ally", and `When.SONT` is the printed
    window.

    The curse itself is `c.curse`, an ordinary verb, so the card the
    spec names for it needs no row of its own.

    **The declared trigger became an outer watch so the ability swap has
    somewhere to be laid.** A row with `on=Trigger(...)` runs its body only
    when the trigger fires, and the card's last sentence is a standing
    property of the character -- laid in there it would arrive only after
    the first cursed enemy fell, which is every earlier roll too late.
    `turns.arm_traits_of` arms an `action=NONE` row with no `on=`, so the
    row becomes a trait that lays the swap and watches for the drop.
    `ranger_b.f1309` is the same rewrite; `trigger=` keeps the card's words.

    So there are two watches now and they nest: the outer one is the pact
    boon firing, the inner one is the single ally it then waits for.

    Only the attack half of "attack rolls and damage rolls" lands. The swap
    is recorded against the creature and `Attack.ability_for` reads it;
    a damage line naming its own modifier belongs to the associated row and
    is not this row's to rewrite. Not claimed as a gap here.
    """
    me = c.me
    for ref in _ASSOCIATED["f3417"]:
        c.rolls_with(ref, CHA)

    def struck(ev: DamageApplied) -> None:
        if ev.source == me or ev.amount <= 0 or ev.source not in c.allies():
            return
        p = get(ev.detail)
        if p is None or not p.is_attack or not c.can_see(ev.source):
            return
        if c.cursed(on=ev.target):
            c.flat(3 + c.int_mod, on=ev.target)
        else:
            c.curse(on=ev.target)

    def fell(ev: Dropped) -> None:
        if not cursed_by_me(c.world, me, ev):
            return
        c.watch(DamageApplied, struck, until=When.SONT, on=me, once=True,
                label=c.ref)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me)


@power("f3418", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3418(c: Cast) -> None:
    """"Once per encounter when you enhance hand of blight, you can forgo
    the extra damage and instead cause the target to shift its speed away
    from you along the safest, fastest path."

    **Re-aimed off `spec.power_ref()` earlier.** The power is `p12887` --
    the one its three siblings f3416, f3420 and f3422 name by ref in the
    same printed sentence; only this block's copy went unscrubbed.

    **"Shift its speed away from you" is the target's own move**, not a
    push -- so it is `c.shift(who=foe, away_from=c.me)` and not `c.slide`.
    Those differ: a slide is forced movement, which "cannot be slid"
    refuses and which this card does not describe. `c.shift` already takes
    both parameters; the first draft of this row named a `c.move_away` that
    does not exist, and said so in a docstring while the body did nothing.

    `c.speed_of(foe)` is "its speed", the target's and not the warlock's --
    which is the default that verb's own docstring warns about.

    "Along the safest, fastest path" needs no code: `_nearest_first` orders
    the options and a headless run takes the first.

    "Once per encounter" is the pact boon's own limit rather than a second
    counter -- fell might is one charge an encounter, so there is no second
    enhancement for this to refuse.
    """
    c.bonus("skill:intimidate", 2, on=c.me, until=When.ENCOUNTER,
            kind="feat")

    def retreat(using: Cast) -> None:
        foe = using.target
        if foe is not None:
            using.shift(using.speed_of(foe), who=foe, away_from=using.me)

    c.pre_empt("p12887", "fell_might_damage", retreat)


@power("f3419", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger=_CURSED_FELL,
       dropped=AUGMENT)
def f3419(c: Cast) -> None:
    """The same three clauses as f3417 and the same split: the shove and the
    ability swap are written, the augment is not.

    Declared trigger turned into a watch for the reason given on `f3417`,
    and the swap is the attack half only on the same reading.
    """
    me = c.me
    for ref in _ASSOCIATED["f3419"]:
        c.rolls_with(ref, CHA)

    def fell(ev: Dropped) -> None:
        if not cursed_by_me(c.world, me, ev):
            return
        for foe in c.enemies():
            if c.adjacent(foe):
                c.push(1, on=foe)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me)


@power("f3420", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3420(c: Cast) -> None:
    """"Forgo the extra damage the augment would deal to instead teleport
    the target a number of squares equal to your Intelligence modifier to an
    unoccupied square adjacent to an ally you can see."

    The destination is the printed constraint and the reason this is
    `c.teleport(toward=)` rather than a bare distance: the square has to be
    beside an ally, which is what `toward` offers closest-first.
    """
    c.bonus("skill:nature", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def fling(using: Cast) -> None:
        foe = using.target
        mates = [a for a in using.allies() if a != using.me]
        if foe is None or not mates or using.int_mod <= 0:
            return
        using.teleport(using.int_mod, who=foe,
                       toward=using.choose(mates, "beside which ally"))

    c.pre_empt("p12887", "fell_might_damage", fling)


@power("f3421", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger=_CURSED_FELL,
       on=Trigger(Dropped, cursed_by_me, _CURSED_FELL),
       dropped=AUGMENT)
def f3421(c: Cast) -> None:
    """"No enemy can be slid more than 1 square by this effect" is what
    the set is for: an adjacent enemy that is also cursed appears in both
    printed groups and is slid once."""
    shoved = {f for f in c.enemies() if c.adjacent(f) or c.cursed(on=f)}
    for foe in sorted(shoved):
        c.slide(1, on=foe)


@power("f3422", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3422(c: Cast) -> None:
    """"Forgo the extra damage the augment would deal to instead weaken the
    target until the end of your next turn."

    The simplest of the seven: one condition, the printed duration.
    """
    c.bonus("skill:bluff", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def sap(using: Cast) -> None:
        foe = using.target
        if foe is not None:
            using.weakened(on=foe, until=When.EONT)

    c.pre_empt("p12887", "fell_might_damage", sap)


@power("f3423", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger=_CURSED_FELL,
       on=Trigger(Dropped, cursed_by_me, _CURSED_FELL),
       dropped=AUGMENT)
def f3423(c: Cast) -> None:
    """`c.enemies` leaves out the dead, so the creature that has just
    fallen is not paid twice."""
    if c.int_mod <= 0:
        return
    for foe in c.enemies():
        if c.cursed(on=foe):
            c.flat(c.int_mod, dtype=DamageType.PSYCHIC, on=foe)
