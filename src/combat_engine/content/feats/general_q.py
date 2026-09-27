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

**The associated-power rider.** Seven martial feats print a skill bonus
*and* "when you use a power associated with this feat and hit an enemy
with it, ...". A row declared with `on=Trigger(...)` never lays its
standing modifiers, so these are traits: the bonus is laid at arm time
and `c.watch(Hit, ...)` carries the rider. Three of the seven print no
Associated Powers line at all, so their rider is `dropped` and their
skill bonus still plays.

**"You can spend 1 power point to ..."** is writable: `c.points()` asks
whether there is one and `c.spend_points(1)` takes it. Five of the
psionic feats here are finished for that reason alone. What is not
writable is reading a pool *back down to zero* (`c.on_points_spent()`)
or handing points out (`c.grant_points()`).

**Prose-named powers.** Nineteen rows are riders on a power the spec
names in words with no ref -- quick formation, disrupting advance,
wasteland fury, the spirit of Athas -- and `spec.power_ref()` is the
symbol that has held that gap since the fourth wave. There is nothing
for `c.watch` to match on.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
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
    Keyword,
    Melee,
    Ranged,
    Trigger,
    UpTo,
    Usage,
    When,
    get,
    power,
    targets_me,
)
from combat_engine.engine.events import (
    ActionSpent,
    ConditionApplied,
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    Hit,
    MoveStart,
    PowerResolved,
    PowerUsed,
    SkillCheck,
)
from combat_engine.engine.query import alive, distance_between, holding, team

#: A power the spec names in prose with no ref, so nothing can watch it.
PROSE = ("spec.power_ref()",)
#: "You swap one of your level N powers for this one." The card is handed
#: over; giving a power up is a build-time exchange.
SWAP = ("chargen.power_swap()",)
#: A class feature named in prose, with no `cf:` ref to borrow.
FEATURE = ("c.class_feature()",)
#: The Associated Powers line is absent from the block.
ASSOCIATED = ("feat.associated_powers",)
#: Augmenting a power from outside its own card.
AUGMENT = ("dsl.use(augment=)",)
#: "Choose a power granted by <feature>" -- features are not rows.
BORROW = ("c.borrow_feature()",)
#: A saving throw does not say what it is being made against.
SAVE_KEYWORDS = ("SavingThrow.keywords",)

MARTIAL = [Keyword.MARTIAL]
WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
PSIONIC = [Keyword.PSIONIC]
WALKED = ("walk", "shift", "run")


# -- small shared questions -------------------------------------------------


def _wielding(what: str):  # noqa: ANN202
    """A printed Requirement naming one weapon, as `exotic.py` writes it.

    False for every character `chargen` can build today, which is why the
    cards below report UNUSED rather than SILENT."""

    def gate(world, eid: int) -> bool:  # noqa: ANN001
        return bool(holding(world, eid, what))

    return gate


def _swap(ref: str, card: str) -> None:
    """The parent half of a swap chain: the card, and nothing else."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, dropped=SWAP)
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


def _on_hit_with(c: Cast, refs: tuple[str, ...], fn) -> None:  # noqa: ANN001
    """"When you use a power associated with this feat and hit an enemy."

    A trait rather than a declared trigger, because each of these feats
    also prints a standing skill bonus and a body under `on=` runs only
    when the trigger fires."""

    def rider(ev: Any) -> None:
        if ev.attacker == c.me and ev.power in refs:
            fn(ev)

    c.watch(Hit, rider, on=c.me, until=When.ENCOUNTER)


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
       reach=PERSONAL, target=SELF, todo=("c.skill_circumstance()",))
def f3177(c: Cast) -> None:
    """Four skill bonuses that apply only to one subject matter. Written
    plain they would be a flat +5 to four skills in every check the
    character ever makes, which is a much larger feat than the printed
    one."""


@power("f3178", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SAVE_KEYWORDS)
def f3178(c: Cast) -> None:
    """A saving throw carries `against` as a free-text label and no
    keywords, so "against charm, illusion and psychic effects" cannot be
    narrowed and the whole benefit is the narrowing."""


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
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3180(c: Cast) -> None:
    """Rides on a power named only in words."""


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
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3183(c: Cast) -> None:
    """Widens the push of a power named only in words."""


_swap("f3184", "f3184b")


@power("f3184b", level=1, cls="", usage=ENCOUNTER, action=MOVE,
       reach=Melee(1), target=ONE_CREATURE, keywords=MARTIAL,
       requires=_wielding("m5466a0"),
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


_swap("f3185", "f3185b")


@power("f3185b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(STR, vs=AC), requires=_wielding("m5466a0"),
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
       attack=Attack(STR, vs=AC), requires=_wielding("m5466a0"),
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


_swap("f3186", "f3186b")


@power("f3186b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Ranged(10), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.RELIABLE, Keyword.WEAPON],
       attack=Attack(STR, vs=REF), requires=_wielding("m5466a0"),
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
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3187(c: Cast) -> None:
    """Adds a second beneficiary to a power named only in words."""


_F3188 = ("p917", "p992", "p704", "p1063")


@power("f3188", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.race()",))
def f3188(c: Cast) -> None:
    """The shift doubles for one race and nothing reads a character's
    race back, so the printed 1 square is what is laid. The difficult
    terrain waiver is held to the end of the turn because it is scoped to
    the shift and nothing scopes an allowance to one move."""
    c.bonus("skill:acrobatics", 1, on=c.me, until=When.ENCOUNTER, kind="feat")
    c.bonus("skill:athletics", 1, on=c.me, until=When.ENCOUNTER, kind="feat")

    def step(ev: Any) -> None:
        c.ignores_difficult(on=c.me, until=When.EOT)
        c.shift(1)

    _on_hit_with(c, _F3188, step)


@power("f3189", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3189(c: Cast) -> None:
    """Fires on dismissing a conjuration a power named in words makes."""


@power("f3190", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3190(c: Cast) -> None:
    """Lets a class feature ride an action point. The feature has no ref
    and nothing announces one being used."""


@power("f3191", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3191(c: Cast) -> None:
    """Adds prone to a push a power named only in words deals out."""


_swap("f3192", "f3192b")


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


_swap("f3193", "f3193b")


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


_swap("f3194", "f3194b")


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
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3195(c: Cast) -> None:
    """A slide and a shift hung on a power named only in words."""


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
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3197(c: Cast) -> None:
    """A daze hung on a power named only in words."""


@power("f3198", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_basic()",))
def f3198(c: Cast) -> None:
    """An attack an ally's power hands you is not marked as one when it
    is rolled, so there is nothing for the bonus to gate on."""


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
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3200(c: Cast) -> None:
    """Fires on dismissing a conjuration a power named in words makes."""


@power("f3201", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3201(c: Cast) -> None:
    """Widens an invisibility a power named only in words grants."""


@power("f3203", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.counts_as(keyword=)",))
def f3203(c: Cast) -> None:
    """Adds a keyword to a named row. Keywords are header data read
    before anything runs and no verb writes one onto a power."""


@power("f3204", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3204(c: Cast) -> None:
    """A free shift hung on a power named only in words."""


_swap("f3206", "f3206b")


@power("f3206b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=MARTIAL,
       requires=_wielding("gouge"),
       requires_text="wielding the weapon this chain names",
       trigger="you hit an enemy with a gouge",
       on=Trigger(Hit, _i_hit, "you hit an enemy"),
       dropped=("c.shift(toward=)",))
def f3206b(c: Cast) -> None:
    """The distance is right and the destination is not: `c.shift` picks
    a square through the world's decider and takes no creature to close
    on, so "to a square adjacent to the enemy" is the dropped half."""
    c.shift(3)


_swap("f3207", "f3207b")


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


_swap("f3208", "f3208b")


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
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3209(c: Cast) -> None:
    """"One of your <feature> attacks" names a set of rows by the feature
    that grants them, and a feature is not a row with members to list."""


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


_swap("f3211", "f3211b")


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


_swap("f3212", "f3212b")


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


_swap("f3213", "f3213b")


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
       reach=PERSONAL, target=SELF, dropped=("chargen.race_choice()",))
def f3214(c: Cast) -> None:
    """The defence is chosen in play because it is a fact about a fight;
    the skill is chosen when the character is made and there is no list
    of skills to offer here, so that half is dropped."""
    pick = c.choose([FORT, REF, WILL], "which defence")
    if pick is not None:
        c.bonus(pick, 1, on=c.me, until=When.ENCOUNTER, kind="racial")


@power("f3215", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an adjacent enemy takes damage from your quarry rider",
       on=Trigger(DamageApplied, lambda w, me, ev: (
           ev.source == me and distance_between(w, me, ev.target) <= 1
       ), "an adjacent enemy takes damage from you"),
       dropped=("c.on_extra_damage()",))
def f3215(c: Cast) -> None:
    """The quarry rider is not announced apart from the blow it rides
    on. `DamageApplied.detail` does exist and carries the power's ref
    -- which is why the marker is not for that field but for
    `c.on_extra_damage()`, the fifteen-row group for exactly this: the
    class's extra damage is paid inside another row's `c.damage` and
    nothing says which of its lines paid. So the trigger here is every
    blow you land on an adjacent quarry, which fires more often than
    printed.

    The 3-at-11th and 4-at-21st steps are paragon and epic; the project
    stops at 10, so the heroic 2 is the whole number."""
    struck = c.trigger.target
    if not c.is_quarry(struck):
        return
    others = [e for e in c.within(1, side="enemy") if e != struck]
    if others:
        c.flat(2, on=others[0])


@power("f3216", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3216(c: Cast) -> None:
    """Extra poison damage on a power named only in words."""


@power("f3217", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.expend_row()",))
def f3217(c: Cast) -> None:
    """Trades a named power's use for temporary hit points. A row can be
    granted and forbidden; spending one without using it has no verb."""


@power("f3218", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED)
def f3218(c: Cast) -> None:
    """The block prints no Associated Powers line, so the rider has no
    set of refs to watch. The skill bonus is the whole of what plays."""
    c.bonus("skill:perception", 1, on=c.me, until=When.ENCOUNTER,
            kind="feat")


@power("f3220", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=(*SAVE_KEYWORDS, "c.resist_forced(when=)"))
def f3220(c: Cast) -> None:
    """The forced-movement half plays and is slightly too generous: it
    is printed only while unbloodied, and `c.resist_forced` takes no
    gate, so a bloodied character keeps the square here."""
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power("f3221", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit against an enemy",
       on=Trigger(Hit, _i_crit, "you score a critical hit"))
def f3221(c: Cast) -> None:
    """`Hit` carries `critical` as a field, so the crit is asked of the
    event rather than of `c.crit`, which is about the caster's own roll
    and is already over by the time a watcher runs."""
    c.grants_advantage(on=c.trigger.target, to=c.me, until=When.EONT)


_swap("f3222", "f3222b")


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


_swap("f3223", "f3223b")


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


_swap("f3224", "f3224b")


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
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3225(c: Cast) -> None:
    """Retypes the damage of a power named only in words."""


@power("f3226", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3226(c: Cast) -> None:
    """Defences hung on a power named only in words."""


@power("f3227", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.curse_damage()",))
def f3227(c: Cast) -> None:
    """Raises and retypes the curse rider. `c.curse` lays a curse and
    nothing reaches the dice it pays out."""


@power("f3228", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.max_surges()",))
def f3228(c: Cast) -> None:
    """A surge can be spent and regained; how many a character has is a
    number on `Health` that no verb writes. The Endurance half is a skill
    reroll out of combat."""


@power("f3230", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED)
def f3230(c: Cast) -> None:
    """No Associated Powers line, so the once-per-encounter advantage has
    nothing to hang on. The skill bonus plays."""
    c.bonus("skill:endurance", 2, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3231", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3231(c: Cast) -> None:
    """Replaces the effect of a power named only in words."""


@power("f3232", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*FEATURE, "c.grant_points()"))
def f3232(c: Cast) -> None:
    """Swaps one class feature's payout for a power point. Neither the
    feature nor handing a point out has a verb."""


@power("f3233", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3233(c: Cast) -> None:
    """Defences hung on a power named only in words."""


_F3234 = ("p917", "p10890", "p704", "p10472")


@power("f3234", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3234(c: Cast) -> None:
    """The plainest of the seven: a skill bonus and a push."""
    c.bonus("skill:athletics", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def shove(ev: Any) -> None:
        c.push(1, on=ev.target)

    _on_hit_with(c, _F3234, shove)


@power("f3235", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3235(c: Cast) -> None:
    """A free saving throw when a class feature comes back. Nothing
    announces a feature recharging."""


@power("f3237", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=(*FEATURE, "c.familiar_state()"))
def f3237(c: Cast) -> None:
    """Pays out when a daily is used *without* a class feature, and the
    beneficiary is picked by standing next to a familiar. Neither the
    feature nor the familiar's position can be asked about."""


@power("f3239", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3239(c: Cast) -> None:
    """A saving-throw penalty hung on a power named only in words."""


@power("f3240", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you take damage from an attack",
       on=Trigger(DamageApplied, targets_me, "you take damage"),
       dropped=("c.effects_on()",))
def f3240(c: Cast) -> None:
    """The printed gate is "while you are affected by <a named row of
    yours>", and nothing lists the effects standing on a creature by the
    row that laid them, so the bonus is paid on any blow.

    `c.bonus(dice=)` is the extra die: a flat `c.damage` here would be a
    second blow rather than a rider on the next one."""
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EONT, once=True,
            when=lambda ctx: _melee(ctx.get("power", "")))


@power("f3242", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3242(c: Cast) -> None:
    """A daze hung on a power named only in words."""


@power("f3243", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3243(c: Cast) -> None:
    """A slide hung on a power named only in words."""


@power("f3244", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3244(c: Cast) -> None:
    """A defence penalty that rides on a class feature being used with a
    daily. The feature has no ref and announces nothing."""


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
       reach=PERSONAL, target=SELF, dropped=("c.vulnerable(once=)",))
def f3246(c: Cast) -> None:
    """Printed as "the *next* attack that hits"; `c.vulnerable` has no
    one-shot form, so as written every hit inside the duration is paid."""
    c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="feat")

    def soft(ev: Any) -> None:
        c.vulnerable(3, on=ev.target, until=When.EONT)

    _on_hit_with(c, _F3246, soft)


@power("f3247", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROSE)
def f3247(c: Cast) -> None:
    """Three powers named by their category and not by ref."""


@power("f3248", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit",
       on=Trigger(Hit, _i_crit, "you score a critical hit"),
       dropped=("c.attack_ability()",))
def f3248(c: Cast) -> None:
    """"Your primary ability modifier" is a fact about the class, not
    about the row being used, and nothing names one. The highest
    modifier stands in, which is right for most builds and generous for
    a few."""
    best = max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod,
               c.cha_mod)
    if best <= 0:
        return
    c.temp_hp(best, on=c.me)
    for friend in c.within(1, side="ally"):
        c.temp_hp(best, on=friend)


@power("f3249", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED)
def f3249(c: Cast) -> None:
    """No Associated Powers line, so the shift has nothing to ride on."""
    c.bonus("skill:acrobatics", 2, on=c.me, until=When.ENCOUNTER,
            kind="feat")


# -- the psionic tail: power points, spent one at a time --------------------


@power("f3274", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.max_surges()", "c.lend_skills()"))
def f3274(c: Cast) -> None:
    """One more healing surge, and one skill standing in for another.
    Neither is a thing a fight does."""


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
       todo=("c.recast(usage=)", "Target.kind"))
def f3292(c: Cast) -> None:
    """Turns an encounter cantrip into an at-will -- `c.recast` changes
    what a row costs, not how often it may be used -- and then hangs
    combat advantage off an enemy standing beside the *object or square*
    the cantrip was aimed at, which is not a target the engine has."""


@power("f3295", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.regain_points()",))
def f3295(c: Cast) -> None:
    """Points can be spent and counted; nothing puts one back."""


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


@power("f3309", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("SavingThrow.bonus",))
def f3309(c: Cast) -> None:
    """"While you have at least 1 power point" is a gate that reads the
    pool at the moment the save is rolled, which is what a `when=` does
    -- the pool empties mid-fight and a bonus laid once would not notice.

    Raising it to +3 has to add to a die already down; `SavingThrow`
    carries `bonus` but only `saved` is read back, so that half is
    dropped."""
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: c.points() > 0)


@power("f3310", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3310(c: Cast) -> None:
    """Both halves land because a trait arms at the top of the fight,
    which is when initiative is rolled -- so the point is offered before
    the number is wanted, and `c.initiative` moves the creature in the
    order once."""
    c.initiative(6 if _point(c) else 3, on=c.me)


@power("f3311", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.boost_attack()",))
def f3311(c: Cast) -> None:
    """The attack context carries `opportunity`, so the standing +1 is a
    plain gated bonus. The +2 is bought *after* the attack is declared
    and nothing adds to an attack roll once it is down."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("opportunity")))


@power("f3312", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.bonus('skill:any')", "c.on_skill_check()"))
def f3312(c: Cast) -> None:
    """A skill chosen when the feat is taken, and a point spent on a
    check as it is made. `c.bonus` wants a named skill and nothing offers
    the option at the moment a check happens."""


@power("f3313", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.max_hp()", "c.on_second_wind()"))
def f3313(c: Cast) -> None:
    """Extra maximum hit points, and a point spent on a second wind.
    `Health.max` is dealt at build time and second wind is an action
    rather than a power, so it announces nothing."""


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
       on=Trigger(PowerUsed, _my_use("p2475"), "you use p2475"),
       dropped=("c.expend_row()",))
def f3329(c: Cast) -> None:
    """The shift is written against the ref the spec gives. Spending the
    same row *unused* to shrug off surprise has no verb, so that half is
    dropped."""
    c.shift(1)


@power("f3389", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*FEATURE, "c.grant_points()"))
def f3389(c: Cast) -> None:
    """Grants a class feature and one power point. Features are not rows
    and nothing adds to a pool."""


@power("f3390", level=1, cls="", usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3390(c: Cast) -> None:
    """"Choose a power granted by <a feature>" -- the feature has no list
    of rows to choose from."""


@power("f3391", level=1, cls="", usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3391(c: Cast) -> None:
    """Same shape: every power a named feature grants, once a day."""


@power("f3392", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*BORROW, "c.lend_skills()"))
def f3392(c: Cast) -> None:
    """Training from another class's skill list, and one of its at-wills
    chosen by level rather than by ref."""


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
    """A power granted by a named feature, once a day."""


@power("f3395", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.set_origin()", "c.telepathy()"))
def f3395(c: Cast) -> None:
    """The card is the combat half and it is handed over. Changing a
    creature's origin and giving it a telepathy range are both facts
    about the character sheet that no verb writes."""
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
       reach=PERSONAL, target=SELF, dropped=("c.set_origin()",))
def f3396(c: Cast) -> None:
    """Same shape as f3395: the card plays, the origin change does not."""
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


@power("f3402", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3402(c: Cast) -> None:
    """Fires on a critical hit inside the radius of a class feature's
    aura. `c.my_aura` finds an aura by label and the feature has none."""


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
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3404(c: Cast) -> None:
    """Retypes the damage of a class feature's attack and makes it bite
    the insubstantial. The feature has no ref."""


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
       reach=PERSONAL, target=SELF, dropped=(*AUGMENT, *PROSE))
def f3416(c: Cast) -> None:
    """Trades an augment's extra damage for a decaying vulnerability on
    a power the spec names in words. The skill bonus is what plays."""
    c.bonus("skill:diplomacy", 2, on=c.me, until=When.ENCOUNTER,
            kind="feat")


@power("f3417", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=(*FEATURE, *AUGMENT, "c.ability_for(ref)"))
def f3417(c: Cast) -> None:
    """Three clauses and no writable one: a class feature coming back, a
    feature spent to augment a listed power, and one ability swapped for
    another on a named set of rows."""


@power("f3418", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=(*AUGMENT, *PROSE))
def f3418(c: Cast) -> None:
    """Same shape as f3416: a skill bonus that plays and an augment on a
    power named only in words."""
    c.bonus("skill:intimidate", 2, on=c.me, until=When.ENCOUNTER,
            kind="feat")


@power("f3419", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=(*FEATURE, *AUGMENT, "c.ability_for(ref)"))
def f3419(c: Cast) -> None:
    """The same three clauses as f3417, with a push and a fear rider."""


@power("f3420", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=(*AUGMENT, *PROSE))
def f3420(c: Cast) -> None:
    """A skill bonus and an augment that teleports instead of hurting."""
    c.bonus("skill:nature", 2, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3421", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*FEATURE, *AUGMENT))
def f3421(c: Cast) -> None:
    """A slide on dropping a cursed enemy, and an augment that makes the
    target swing at somebody. Both hang off the class feature."""


@power("f3422", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=(*AUGMENT, *PROSE))
def f3422(c: Cast) -> None:
    """A skill bonus and an augment that weakens instead of hurting."""
    c.bonus("skill:bluff", 2, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3423", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*FEATURE, *AUGMENT))
def f3423(c: Cast) -> None:
    """Psychic damage on dropping a cursed enemy, and an augment that
    turns the caster insubstantial. Both hang off the class feature."""
