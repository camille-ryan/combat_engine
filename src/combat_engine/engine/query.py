"""Facts derived from the board, asked rather than stored.

Combat advantage is the reason this module exists. A dozen unrelated things
grant it -- flanking, prone, blinded, stunned, a power that says so -- and
storing a flag means every one of them has to remember to take it back. So
nothing stores it; it is recomputed from the board whenever an attack asks.
"""

from __future__ import annotations

from functools import cache, lru_cache
from typing import TYPE_CHECKING, Any

from .components import (
    Barrier,
    Build,
    Companion,
    Conditions,
    Conjuration,
    # Two spellings, two different components, and this is the one holding
    # resistance. `Defenses` above is AC/Fortitude/Reflex/Will.
    Defences,
    Defenses,
    Health,
    Mods,
    Movement,
    Position,
    Powers,
    Shapes,
    Side,
    Stats,
)
from .conditions import rules, rules_for
from .grid import Square, between, linked_spread, spread
from .types import (
    DEFENCES,
    Condition,
    Cover,
    DamageType,
    Defense,
    Light,
    Relation,
    Team,
)

if TYPE_CHECKING:
    from .ecs import World


def since_turn_began(world: World, eid: int) -> list[Any]:
    """Everything that has happened since this creature's own turn began.

    **The log is the only record of what a creature has done or had done to
    it.** Nothing on a creature remembers who hurt it or what it has
    already hit, and a flag would need its own reset watch for a fact the
    log already answers.

    This module held **no log walk at all** before, which is why 63 content
    files grew their own: 74 functions reach into `world.bus.log`, 21 of
    them bounded exactly this way, and five helper names are defined in
    more than one file -- `_hit_me_since_my_turn` in three. Each copy
    re-derived the same two subtleties:

    * the scan stops at **this creature's** `TurnStart`, not at any;
    * a **ghost** turn does not count. A ghost turn is a dead creature's,
      ticked so durations measured against it can end, so the branch is
      unreachable for a creature actually using a row -- which is why one
      of the three copies omitted it with no consequence. Kept here
      because a shared reader should settle the question rather than leave
      21 authors to flip a coin on it.

    Oldest first, so a caller reading "the enemy you hit this turn" gets
    them in the order they happened.
    """
    from .events import TurnStart

    out: list[Any] = []
    for past in reversed(world.bus.log):
        if isinstance(past, TurnStart) and past.actor == eid and not past.ghost:
            break
        out.append(past)
    out.reverse()
    return out


def my_hits_this_turn(world: World, eid: int) -> list[Any]:
    """Every blow this creature has landed since its own turn began.

    The reader for "you must have hit an enemy during this turn", which
    three rows print and six rows' docstrings each claimed was unrecorded.
    It was recorded all along -- `monsters/level_05/lurkers_sa._landed_with`
    has been doing it as a `requires=` gate -- just not anywhere another
    row could reach.

    **Returns the hits, not a yes or no**, because the cards need more than
    the Requirement: `i3151p1` teleports allies *"adjacent to the enemy you
    hit this turn"*, so it needs the victim, and `p15928` narrows to "a
    weapon attack", so it needs each hit's power to ask its header. A bool
    would have served one row of the three.
    """
    from .events import Hit

    return [e for e in since_turn_began(world, eid)
            if isinstance(e, Hit) and e.attacker == eid]


def my_misses_this_turn(world: World, eid: int) -> list[Any]:
    """Every swing this creature has **missed** with since its turn began.

    The mirror of `my_hits_this_turn`, and not a nicety: `i1132p1` prints
    *"you must have **missed** an enemy with a melee attack during this
    turn"* and then attacks "the same enemy". Nothing else in the corpus
    reads a miss this way, but one row needing it is the difference
    between the row being written and being mis-marked -- and it *was*
    mis-marked, by me, at `81e1e08`: I re-pointed it to a hit-shaped
    symbol off a docstring that had said "hit or missed" and been right.

    `Miss` carries the same `attacker` and `target` as `Hit`, so this is
    the same walk with one isinstance changed.
    """
    from .events import Miss

    return [e for e in since_turn_began(world, eid)
            if isinstance(e, Miss) and e.attacker == eid]


def hit_me_this_turn(world: World, eid: int) -> set[int]:
    """Who has landed a blow on this creature since its turn began.

    The mirror of `my_hits_this_turn`, and the one that already existed --
    three times, in `monsters/level_04/lurkers_sa`,
    `monsters/level_04/skirmishers_sa` and `monsters/level_12/soldiers_sa`,
    each as a private `_hit_me_since_my_turn`.

    **Ask it inside the gate, never when the action is spent.** A creature
    spends a minor action before being hit as often as after, so a set
    taken early is stale the moment anybody lands a blow -- the point
    `soldiers_sa`'s copy makes and the reason this is a function rather
    than something cached.
    """
    from .events import Hit

    return {
        e.attacker for e in since_turn_began(world, eid)
        if isinstance(e, Hit) and e.target == eid
    }


def creatures(world: World) -> list[int]:
    """Everything that can be targeted, flanked, covered or walked around.

    A companion is one of these. It has hit points and a square and is a
    legitimate target, which is the whole reason it is not a `Conjuration`.
    """
    return list(world.having(Health, Position))


def combatants(world: World) -> list[int]:
    """The narrower question: who takes turns and decides the fight.

    `creatures` answered four questions at once -- the initiative roster,
    the target pool, the win condition and the render list -- and that was
    fine for as long as everything on the board wanted the same answer to
    all four. A companion wants to be targeted and wants no turn, so the
    questions had to come apart. Only three callers need this one, all in
    `turns.py`: rolling initiative, `over`, and `winner`.

    Kept as a subtraction rather than a component test at every call site,
    so anything later that is targetable-but-not-a-combatant lands here by
    adding itself to one list.
    """
    return [
        e
        for e in creatures(world)
        if world.get(e, Companion) is None
        and world.get(e, Barrier) is None
        # An attackable conjuration -- a shade, an illusory double. It has
        # `Health` so that it can be aimed at and killed, and that is the
        # only reason; it takes no turn and does not decide the fight.
        # Added here rather than tested at every call site, which is what
        # the paragraph above asks for. #714.
        and world.get(e, Conjuration) is None
    ]


def squares(world: World, eid: int) -> frozenset[Square]:
    pos = world.get(eid, Position)
    return pos.squares if pos else frozenset()


def team(world: World, eid: int) -> Team | None:
    side = world.get(eid, Side)
    return side.team if side else None


def allies(world: World, eid: int, *, companions: bool = False) -> list[int]:
    """Allies never include the creature itself, nor anybody's companion.

    A companion is on your side and in the target pool, which is what makes
    it targetable -- and it meant "each ally adjacent to your spirit
    companion" healed, buffed or slid the spirit itself. Silently: the row
    read correctly and did one thing too many, and three shaman rows had to
    filter it out by hand before this default existed.

    `companions=True` for the rare row that really does mean the pet.
    """
    mine = team(world, eid)
    if mine is None:
        return []
    return [
        o
        for o in creatures(world)
        if o != eid
        and team(world, o) is mine
        and (companions or world.get(o, Companion) is None)
        # A wall you raised stands on your side so that your enemies may
        # attack it. It is not an ally: "each ally in the burst" would heal
        # the masonry.
        and world.get(o, Barrier) is None
        # And a shade you conjured, for the same reason and with the same
        # consequence if it were left in: it stands on your side so that
        # your enemies may attack it, and "each ally within 5" must not
        # heal it or buff it. #714.
        and world.get(o, Conjuration) is None
    ]


def enemies(world: World, eid: int) -> list[int]:
    mine = team(world, eid)
    if mine is None:
        return []
    return [
        o
        for o in creatures(world)
        if team(world, o) is not None and team(world, o) is not mine and alive(world, o)
    ]


#: The one load property the table prices. Seven weapons print `load free`
#: and three print this; nothing prints a third form. Named rather than
#: spelled inline at each site, because a misspelling here reads exactly
#: like a weapon that needs no loading -- the uniformly-dead gate this
#: repository keeps finding.
COSTED_LOAD = "load minor"


def needs_loading(weapon: Any) -> bool:
    """Does firing this weapon leave it empty until somebody reloads it?

    True only for the three weapons whose printed properties include
    `load minor` -- `w3629` crossbow, `w3659` superior-crossbow, `w3662`
    blowgun. `load free` is a load the rules charge nothing for, so a
    weapon carrying it is always ready and this answers False; so does
    every weapon with no load property at all, which is most of them.

    A free function rather than a `Weapon` method because `Weapon` is a
    data record read by the ETL, the wire and `chargen` alike, and the
    question is the engine's. #675, #725.
    """
    return COSTED_LOAD in (getattr(weapon, "properties", None) or ())


def ready_to_fire(world: World, eid: int, weapon: Any) -> bool:
    """Is this weapon loaded, for a creature that has to load it?

    **A weapon that needs no loading is always ready**, which is the half a
    caller must not have to remember: asking this about a longbow has to
    answer True, or every bow in the game stops firing.
    """
    from .components import Gear

    if not needs_loading(weapon):
        return True
    gear = world.get(eid, Gear)
    if gear is None:
        return True
    return getattr(weapon, "ref", "") not in gear.unloaded


def holding(world: World, eid: int, what: str = "") -> list[Any]:
    """What this creature has in hand, filtered by a printed word.

    `""` is everything held. `"magic"` is anything with an enhancement
    bonus, which is what "a creature wielding a magic item" means; anything
    else is matched the way `c.wielding` matches it -- a group, a property,
    or `"implement"`.
    """
    from .components import Gear

    gear = world.get(eid, Gear)
    if gear is None:
        return []
    out = list(gear.held)
    if what == "magic":
        return [w for w in out if w.enhancement > 0]
    if what:
        # By name as well as by group. A card naming one weapon -- "you
        # must be wielding a whip" -- has no group to ask for: a whip is
        # filed under flail, and so are thirteen other things.
        #
        # **`slug`, not `ref`.** This built `f"w:{what.replace(' ', '-')}"` and
        # compared it to the ref, which only worked while a ref *was* the
        # slugified name. The ref is the compendium id now (#339) and the name
        # has its own field, so the question is asked of the field that answers
        # it. It would not have raised -- it would have matched nothing.
        # **A ref matches too, and content needs that one.** A card saying
        # "you must be wielding <one named weapon>" has no group to ask for,
        # and the only other handle was the slug -- which *is* the printed
        # name, and a printed name may not enter a tracked file. So a row
        # obeying the naming rule had nothing to pass, and `general_q`'s
        # four `_wielding(...)` sites show what that costs: somebody
        # resolved the name to a ref and got `m5466a0`, a **monster power**
        # that happens to share the weapon's printed name. The Requirement
        # was false for every creature in the game and the docstring
        # rationalised it as a chargen limitation.
        named = what.replace(" ", "-")
        return [
            w for w in out
            if what in w.properties or w.group == what or w.category == what
            or w.slug == named or w.ref == what
        ]
    return out


def scenery(
    world: World,
    kind: str = "",
    *,
    within: int = 0,
    of: int | None = None,
    loose: bool = False,
) -> list[int]:
    """What is standing on the map that is not a creature.

    `kind` is the printed word -- "fire", "object" -- and `""` is all of it.
    `within` measures from `of`, which is what a Requirement line reading
    "you must be adjacent to a fire" asks; `loose` drops the ones bolted
    down or in somebody's hands.

    A module-level function as well as `c.scenery`, because a `requires=`
    gate is handed `(world, eid)` and no `Cast` -- the same split
    `moving_as` has.
    """
    from .components import Scenery

    out = []
    for eid, thing in sorted(world.each(Scenery)):
        if kind and thing.kind != kind:
            continue
        if loose and (thing.fastened or thing.by):
            continue
        if within and (of is None or distance_between(world, of, eid) > within):
            continue
        out.append(eid)
    return out


def alive(world: World, eid: int) -> bool:
    h = world.get(eid, Health)
    return h is not None and h.hp > h.dying_at


def surge_value(world: World, eid: int) -> int:
    """What one healing surge is worth: a quarter of maximum, modified.

    `Health.surge_value` is a property computed on every read, so there was
    nothing to hang a change on and two races print one. Read through here
    the way `speed` is, so a single `c.bonus("surge_value", n)` reaches
    every place a surge is cashed -- the second wind and the natural
    twenty on a death save included -- rather than only the rows that
    happened to ask the same way.
    """
    health = world.get(eid, Health)
    if health is None:
        return 0
    mods = world.get(eid, Mods)
    base = health.surge_value + (mods.total("surge_value") if mods else 0)
    return max(0, base)


def targetable(world: World, eid: int) -> bool:
    """Can a power be aimed at this, and land on it?

    `alive` was the whole answer for as long as everything on the board had
    hit points. Scenery has none and is still a legitimate target -- "one
    Medium or smaller object" is a printed target line -- and `alive` is
    false for it forever, so a row aimed at a crate was dropped between
    being chosen and being run without a word.
    """
    from .components import Scenery

    return alive(world, eid) or world.get(eid, Scenery) is not None


#: The label a `c.considered_bloodied` hold carries. One string, read in
#: two places, so neither can drift from the other.
COUNTS_AS_BLOODIED = "counts-as-bloodied"


def bloodied(world: World, eid: int) -> bool:
    """Is this creature bloodied -- by its hit points, or by a card saying so.

    **`Health.bloodied` is the arithmetic and not the whole question.** Four
    printed rows make a creature count as bloodied *without* taking it
    there -- "bloodied for all purposes" -- and a property on the component
    has no `world` in scope, so it cannot see an effect. The arithmetic
    stays where it is and this is the question.

    A module-level function as well as `Cast.bloodied`, because a
    `requires=` gate is handed `(world, eid)` and no `Cast` -- which is why
    eleven of the hand-rolled reads in `content/` are walrus expressions
    inside a lambda. There was nothing to call. #716.
    """
    from .components import Health

    health = world.get(eid, Health)
    if health is not None and health.bloodied:
        return True
    return any(
        eff.label == COUNTS_AS_BLOODIED for eff in world.effects.of(eid)
    )


def conscious(world: World, eid: int) -> bool:
    return alive(world, eid) and not is_(world, eid, Condition.UNCONSCIOUS)


def is_(world: World, eid: int, c: Condition) -> bool:
    conds = world.get(eid, Conditions)
    return conds is not None and conds.has(c)


def active(world: World, eid: int) -> list[Condition]:
    conds = world.get(eid, Conditions)
    return conds.active if conds else []


def familiar_of(world: World, eid: int) -> int | None:
    """The familiar this creature keeps, whichever mode it is in.

    The selection `Cast.familiar` has always made, moved here because the
    *other* half -- "and is it active" -- was hand-written in four content
    files under four different names, and two of them are `requires=` gates
    that get `(world, eid)` and no `Cast` at all. One of the two shapes had
    to live somewhere both could reach.

    A familiar is a `Companion` with `kind == "familiar"`, falling back to
    whatever single companion the creature has when nothing named one. The
    fallback cannot pick the wrong body: a class that keeps a familiar keeps
    no spirit and no beast.
    """
    mine = [
        e for e in world.having(Companion)
        if world.get(e, Companion).owner == eid  # type: ignore[union-attr]
    ]
    named = [e for e in mine if world.get(e, Companion).kind == "familiar"]  # type: ignore[union-attr]
    if named:
        return named[0]
    return mine[0] if mine else None


def familiar_active(world: World, eid: int) -> int | None:
    """The familiar, if the printed cards would call it active.

    *"Requirement: your familiar must be in its active state"* is printed on
    six rows across three files, and each file asked it by hand off
    `Companion.passive` alone. **That is one condition short.** A destroyed
    familiar keeps its `Companion` row -- `resolve._die` leaves the body an
    entity on purpose -- and `passive` is not a field death touches, so a
    corpse answered "active" for ever and every one of those six rows paid
    out on it.

    So: owned, a familiar, not passive, **and not dead**.

    The last clause has one waiver, and it is a printed one rather than a
    convenience: `f2257` is *"when your familiar is destroyed, treat your
    familiar as in its active state until the end of your next turn"*. That
    is exactly this test being told to skip its new half, for a span, so it
    is read here as a modifier on the **owner** -- not on the familiar,
    whose own effects `_die` tears down, and which would be the one place a
    waiver about being dead could not survive.
    """
    who = familiar_of(world, eid)
    if who is None:
        return None
    pet = world.get(who, Companion)
    if pet is None or pet.passive:
        return None
    if is_(world, who, Condition.DEAD) and not familiar_echoes(world, eid):
        return None
    return who


def familiar_echoes(world: World, eid: int) -> bool:
    """Is this creature's familiar held in its active state past death?

    `f2257`'s span. Gated through `Mods` on the owner, the convention
    `may_enter` and `immune_to` use, so the duration is an ordinary effect
    that an ordinary turn boundary ends.
    """
    mods = world.get(eid, Mods)
    if mods is None or not mods.items:
        return False
    return mods.total("familiar_past_death", {"owner": eid}) > 0


def distance_between(world: World, a: int, b: int) -> int:
    return between(squares(world, a), squares(world, b))


def adjacent(world: World, a: int, b: int) -> bool:
    """Next to each other -- **or joined by a link.**

    A link makes two squares adjacent "for movement or making melee
    attacks", and `Grid.links` was read by `movement.reachable` and
    nothing else, so the melee half of the printed sentence was silently
    dropped. The cost is one `dict.get` on a mapping that is empty in
    every fight where nobody has made a link.
    """
    mine = squares(world, a)
    theirs = squares(world, b)
    if spread(mine, 1) & theirs:
        return True
    return bool(world.grid.links and linked_spread(world.grid.links, mine, 1) & theirs)


# -- numbers ----------------------------------------------------------------


def moving_as(world: World, eid: int, mode: str) -> bool:
    """Is this creature moving that way right now?

    Here as well as on `Cast` because `requires=` is handed `(world, eid)`
    and no `Cast` exists yet -- so a Requirement could not say the same
    sentence the body says, and had to read the component directly. The same
    split `has_combat_advantage` already has.
    """
    mv = world.get(eid, Movement)
    return bool(mv and mv.using == mode)


def charging(world: World, eid: int) -> bool:
    """Is this creature in the middle of a charge?

    Not the same question as the attack context's `charge`, and the
    difference is the whole reason this exists. That key says *this attack
    is the charge's attack* and is read by whoever is swinging; three rows
    ask about the creature **doing** the charging, and one of them is a
    defence bonus -- so the attack it has to survive is somebody else's
    opportunity swing provoked on the way in, where the attacker's context
    carries no charge at all.

    True from the first step of the run to the end of the swing, which is
    what "while charging" spans. `Movement.charging` is the flag and
    `actions.execute` and `Cast.charge_at` are the two doors that set it.
    #732.
    """
    mv = world.get(eid, Movement)
    return mv is not None and mv.charging


def moved_this_action(world: World, eid: int) -> int:
    """How many squares this creature entered during its current move action.

    The number the printed Stealth rule is about -- *"-5 if you moved more
    than 2 squares during that action"* -- and nothing counted it, so the
    penalty had no value and four rows that only ever waive it had nothing
    to waive. #784.

    **Squares, not budget.** `movement.walk` returns a cost that charges 2
    for a difficult square, so a creature that crossed two squares of rough
    ground has spent 4 and moved 2. The card counts squares.

    0 between move actions and at the top of a turn, so a creature that has
    not moved reads 0 rather than whatever it did last turn.
    """
    mv = world.get(eid, Movement)
    return mv.went if mv is not None else 0


def ran_this_action(world: World, eid: int) -> bool:
    """Was this creature's current move action a **run**?

    The other half of the Stealth rule, where running is -10 rather than
    -5. Off `Movement.went_kind`, which `movement.walk` stamps from the
    `kind` it was handed -- the same word `MoveStart.kind_` carries and
    `movement.PRICED_KINDS` prices, so "ran" needed no new bookkeeping.
    """
    mv = world.get(eid, Movement)
    return mv is not None and mv.went_kind == "run"


def speed(world: World, eid: int, ctx: dict[str, Any] | None = None) -> int:
    """How far this creature moves, for the kind of move it is making.

    `ctx` is the attack context's `{"charge": True}` and nothing else so far.
    It was `{}` at every call site, so "+4 to speed when charging" -- a gate
    on a key the context did not carry -- was silently false, and ungating it
    would have been a bonus to all movement, which is not the printed line.
    The three places that measure a charge's run pass the word; everything
    else measures an ordinary move and passes nothing.
    """
    mv = world.get(eid, Movement)
    if mv is None:
        return 0
    base = mv.speed
    mods = world.get(eid, Mods)
    if mods is not None:
        base += mods.total("speed", ctx or {})
    halved = False
    for c in active(world, eid):
        # `rules_for`, not `rules`: a dozen rows waive part of what a
        # condition costs without lifting the condition itself. #508.
        r = rules_for(world, eid, c)
        cap = r.speed_cap
        if cap is not None:
            base = min(base, cap)
        halved = halved or r.halve_speed
        if r.cannot_move:
            return 0
    if halved:
        base //= 2
    return max(0, base)


def level_term(world: World, eid: int, scale: str) -> int:
    """What this creature's level is worth, under the current setting."""
    stats = world.get(eid, Stats)
    level = stats.level if stats else 1
    if scale == "pc":
        return world.scaling.pc(level)
    if scale == "monster":
        return world.scaling.monster(level)
    return 0


def defence(world: World, eid: int, d: Defense, ctx: dict | None = None) -> int:
    """A defence as the attacker sees it: base, level, modifiers, conditions.

    The stored value has no level in it -- see `engine/scaling.py` -- so this
    is the one place a defence gains one, and turning scaling off turns it
    off everywhere at once.

    **`Defense.ANY` resolves here**, to the lowest of the four. A printed
    "vs. Any" hits if it would hit any defence, and one roll against the
    weakest answers that identically -- so the whole construction is a
    lookup rather than four rolls. Doing it here rather than in a row is
    what makes it correct: the row that needed it first chose its target
    defence from `Defenses.base`, which carries no level, no modifier and
    no condition, so a creature whose Reflex was being penalised was still
    attacked on whatever it was weakest at before the fight started. #360.
    """
    if d is Defense.ANY:
        return min(defence(world, eid, each, ctx) for each in DEFENCES)
    defs = world.need(eid, Defenses)
    base = defs.base(d) + level_term(world, eid, defs.scale)
    mods = world.get(eid, Mods)
    if mods is not None:
        base += mods.total(d.value, ctx or {})
    for c in active(world, eid):
        base += rules_for(world, eid, c).defences.get(d, 0)
    return base


def attack_penalty(world: World, eid: int) -> int:
    """What the attacker's own conditions cost it, before modifiers."""
    return sum(rules_for(world, eid, c).attack for c in active(world, eid))


def deals_half(world: World, eid: int) -> bool:
    return any(rules_for(world, eid, c).weakened for c in active(world, eid))


@cache
def deals_damage(ref: str) -> bool:
    """Does this power *normally* deal damage -- from either of the two
    places damage comes from?

    **The header alone is the trap, and `i1560p1`'s own docstring called
    it.** Several cards end "if the power doesn\'t normally deal damage, no
    extra damage is dealt", and `get(ref).damage is None` looks like the
    question. It is not: **3,518** declared rows carry `damage=None` in the
    header and deal damage in the body through `c.damage`, `p992` among
    them. A header-only gate would have suppressed the rider on most of the
    rows that should get it -- which is the fault pointed the other way, and
    the reason that row carried a symbol instead of a fix.

    So both places are read: the declared expression, or a damage call in
    the body. `7,015` rows say it in the header, `3,518` only in the body.

    **"Normally" is the row, not the roll.** A power that happens to roll
    zero still normally deals damage, and one that deals it only through a
    *rider* does not -- so this reads what the row can do and never the
    event.

    Cached: the answer is static for a given ref, and it reads source.
    Unknown ref answers **False**, because a rider cannot pay out on a power
    nobody declared and the alternative pays on every typo. #782.
    """
    import ast
    import inspect
    import textwrap

    from .dsl import get

    row = get(ref)
    if row is None:
        return False
    if row.damage is not None:
        return True
    fn = next((getattr(row, a) for a in ("body", "fn", "func")
               if callable(getattr(row, a, None))), None)
    if fn is None:
        return False
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError, SyntaxError):
        return False
    # **`ast`, not a regex over the source.** `inspect.getsource` includes
    # the docstring, and a row explaining *why* it does not call `c.damage`
    # would have matched a text search -- a false positive in the direction
    # that pays the rider on a power the card excludes. A `Call` node cannot
    # be in a docstring or a comment.
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"damage", "flat", "ongoing"}
        for n in ast.walk(tree)
    )


#: Roles whose whole point is to stay out of melee, whatever else they can
#: also do. Read alongside what a creature *can* reach with, because the two
#: answer different questions.
_STANDOFF = {"artillery", "controller", "lurker"}


def range_profile(world: World, eid: int) -> str:
    """What this creature can reach with: melee, ranged, hybrid, or none.

    Derived from its own declared rows rather than written down anywhere.
    A hand-applied tag would be one more thing to keep in step with the
    content, and the content already says it -- every row carries its reach
    in the header, which is exactly the point of the header being data.
    """
    from .components import Powers
    from .dsl import branches_for, get, reach_of

    known = world.get(eid, Powers)
    if known is None:
        return "none"
    near = far = False
    for ref in known.all:
        p = get(ref)
        if p is None or not p.is_attack:
            continue
        # Through the per-creature readers: a feat that offers this creature
        # a ranged aiming of a melee row changes what it *prefers*, and the
        # AI reads this to decide whether to close. Reading the print alone
        # made the fourth site the one the grant was missed at. #614.
        for branch in branches_for(world, eid, p):
            kind = reach_of(world, eid, p, branch).kind
            far = far or kind in ("ranged", "area_burst")
            near = near or kind in ("melee", "close_burst", "close_blast")
    if far and near:
        return "hybrid"
    return "ranged" if far else "melee" if near else "none"


def prefers_range(world: World, eid: int) -> bool:
    """Does this creature want to be *out* of melee?

    Capability alone does not say. Nearly every ranged monster also carries
    a melee basic, so by reach almost none of them are purely ranged -- at
    the heroic tier it is 44 melee and 25 hybrid, and not one pure shooter.
    What separates an artillery that happens to have claws from a brute
    that happens to throw something is the role it was written for, which
    the stat block already records.
    """
    profile = range_profile(world, eid)
    if profile in ("melee", "none"):
        return False
    if profile == "ranged":
        return True
    return (stat_block(world, eid).get("role") or "") in _STANDOFF


def stat_block(world: World, eid: int) -> dict[str, Any]:
    """The compendium row behind a creature, or `{}` if it has none.

    **The one place `query` reaches into `content`.** `engine/CLAUDE.md` counts
    those sites and asks that no sixth be added; this is written so there is one
    fewer. It was two reads of the identical shape -- `standoff` here and
    `Cast._stat_block` -- and `Cast` now delegates, so the seam goes from five
    sites to four.

    A character, a companion and a summon are all typeless: only an `Ident`
    naming an `m` ref has a block to read.
    """
    from .components import Ident

    ident = world.get(eid, Ident)
    if ident is None or not ident.ref.startswith("m"):
        return {}
    from combat_engine.content.loader import load

    try:
        return load(ident.ref).row
    except Exception:          # a ref with no row is simply typeless
        return {}


def race_of(world: World, eid: int) -> str:
    """A character's race, by ref -- `r4` -- or `""` for anything without one.

    **The race was on the board all along.** #411 reports it "discarded at
    creation and cannot be recovered", and two content files say the same in
    their docstrings ("nothing carries a creature's race"). It is in
    `Build.choices` as `race:<ref>`, put there deliberately and documented on
    `chargen.Character.race` -- the same way the warlock's pact element rides
    there. What was missing was a reader, which is why three separate rows
    worked around it: a local `_has_race` in `items/head.py` scanned `Powers.known` for an
    `rt:<race>-` trait, and two more rows carry `dropped=("c.race_of()",)`
    having named this verb exactly.

    **A ref, never a word.** `kinds_of` answers a creature's *type* words and a
    race is not one of them -- a character has no type line, and the origin
    sentence 21 races print gives a shared word (`fey` is r3's and r4's and
    every other fey creature's), so matching on it answers the wrong question.
    The ref is also the only spelling allowed in a tracked file: `cls` holds
    `r33` for a racial power for precisely this reason.

    Empty for a monster, which carries its race in its own type line and should
    be asked with `is_kind` instead.
    """
    from .components import Build

    held = world.get(eid, Build)
    if held is None:
        return ""
    for choice in held.choices:
        if choice.startswith("race:"):
            return choice.split(":", 1)[1]
    return ""


@lru_cache(maxsize=1)
def _race_skills() -> dict[str, tuple[tuple[str, int], ...]]:
    """`race_skill`, by race ref. One read of the database, cached.

    A race absent from the mapping printed no skill-bonus line. See the
    table's own comment: for `r7` that is a **fact** -- its benefit is an
    extra trained skill of the character's choosing -- and for nine variant
    races it means the page restates only its differences from a parent. A
    reader must not fill either one in. #694.
    """
    from combat_engine.db import game

    out: dict[str, list[tuple[str, int]]] = {}
    try:
        rows = game().execute("SELECT race, skill, bonus FROM race_skill")
    except Exception:
        return {}
    for race, skill, bonus in rows:
        out.setdefault(race, []).append((skill, int(bonus)))
    return {race: tuple(pairs) for race, pairs in out.items()}


def race_skills(race: str) -> tuple[tuple[str, int], ...]:
    """Which skills that race is good at, as `(skill, bonus)` pairs.

    The racial twin of `class_skill`, which `chargen` has read since #565.
    `race_of` answers *which* race a character is and said nothing about
    what it is good at, and `f2900` is the row that needs the second half:
    *"a +2 racial bonus to one skill to which the chosen race gains a
    bonus"*. #694.

    **Takes a ref, like everything else about a race** -- `race_skills("r1")`
    -- and not a creature, because the race a row asks about is often not
    the one the character is: `f2900`'s is a race the changeling *imitates*.
    Ask `race_of` first when the caster's own is what is wanted.

    Empty for a race printing no such line, and that is not the same as "no
    bonus to anything": see `_race_skills`.
    """
    return _race_skills().get(race, ())


@lru_cache(maxsize=1)
def race_sizes() -> dict[str, str]:
    """Every printed race's ref and size word, from the database.

    Here because "any Medium humanoid" is a printed pool and not a list
    anybody should keep by hand: `p2472` prints exactly that, and `f2900`
    chooses out of it. Lowercase, and empty for the nine variant races whose
    page leaves the column blank and prints the size in their traits.
    """
    from combat_engine.db import game

    try:
        return {ref: (size or "").lower()
                for ref, size in game().execute("SELECT ref, size FROM race")}
    except Exception:
        return {}


def races_sized(size: str) -> tuple[str, ...]:
    """Every race of that printed size, by ref, in ref order.

    `races_sized("medium")` is the pool `p2472` prints -- "the appearance of
    any Medium humanoid" -- and the one `f2900` chooses a race from.
    """
    want = size.strip().lower()
    return tuple(sorted(
        ref for ref, printed in race_sizes().items() if printed == want
    ))


def _type_word(raw: str) -> str:
    """One type word, as a power asks for it.

    The compendium's type line parenthesises its subtypes -- `"(undead)"`,
    `"spider)"`, `"(mount"` -- and 60 of the 144 distinct words carry a
    stray bracket on at least one block, `undead` on all 393 of them. So the
    strip is not cosmetic: without it `c.is_kind("undead")` is False
    everywhere.

    **Pulled out so `kinds_of` and `printed_kinds` cannot disagree.** They
    did for one draft: `printed_kinds` read the raw column and reported
    `spider` absent from a corpus with 33 spiders in it, which nearly got
    filed as a 393-block ETL bug. The live reader had been right all along.
    """
    return raw.strip("() ,.").lower()


@lru_cache(maxsize=1)
def feat_categories() -> dict[str, str]:
    """Every feat's printed category, by ref, from the database.

    The bracket after a feat's printed name -- `feat.category` -- and the
    only thing in this engine that reads it. Nine feats carry `Rune`, and
    `f2613` pays a bonus "equal to the number of rune feats you have".

    **The table is also the test for what a feat is.** A feat is an ordinary
    row in `Powers.known` with nothing in its header to mark it one, so
    "which of these refs are feats" was unanswerable from the registry;
    being in this table is exactly it.

    Cached: one query, and the database does not change inside a run -- the
    bargain `printed_kinds` below strikes for the same reason.
    """
    from combat_engine.db import game

    try:
        return {ref: (category or "") for ref, category in game().execute(
            "SELECT ref, category FROM feat")}
    except Exception:
        # A tree with no built database still has to answer. Content asks
        # this through `c.feats`, and a row raising because `game.db` is
        # absent would be a worse fault than a count of nought.
        return {}


def feats_of(world: World, eid: int, category: str = "") -> tuple[str, ...]:
    """The feats this creature has, by ref, optionally of one category.

    `f2613`, `f2614` and `f2615` all pay something "equal to the number of
    rune feats you have", and nothing counted a character's feats at all --
    `RUNE_FEATS = ("c.feats(category=)",)` is the marker all three carried
    and `defenders_b.py` has held that spelling since before the reader
    existed. #692.

    **Matched as a substring, case-folded**, because two cells carry a comma
    and one of them is a single category naming three classes -- `leaks.py`'s
    category walk records measuring that rather than splitting on it. "Rune"
    matches `Rune` and nothing else in the corpus.
    """
    known = world.get(eid, Powers)
    if known is None:
        return ()
    every = feat_categories()
    mine = [ref for ref in known.known if ref in every]
    if category:
        want = category.strip().lower()
        mine = [ref for ref in mine if want in every[ref].lower()]
    return tuple(mine)


@lru_cache(maxsize=1)
def printed_kinds() -> frozenset[str]:
    """Every type word the corpus prints, from the database.

    The vocabulary `kinds_of` answers *out of*, enumerated for the one
    caller that has to validate a word before any creature exists to ask
    about: `c.ignores_difficult(made_by=)`, which takes a sort of creature
    and must refuse a sort of going.

    **Not a hand-kept set**, and that is the point -- there are 101 of these
    and they come off `monster.keywords`, `monster.kind` and
    `monster.origin`, so a literal list here would be wrong by the next
    import. `DIFFICULT_LABELS` is a closed set because *nothing* writes a
    sort of going but this engine; type words are data.

    Cached: one query, read at validation time, and the database does not
    change inside a run.
    """
    import json

    from combat_engine.db import game

    out: set[str] = set()
    with game() as db:
        for row in db.execute(
            "SELECT keywords, kind, origin FROM monster"
        ).fetchall():
            out |= set(json.loads(row[0] or "[]"))
            for word in (row[1], row[2]):
                if word:
                    out.add(word)
    # The same strip `kinds_of` applies, through the same function.
    return frozenset(w for w in (_type_word(w) for w in out) if w)


def on_build(world: World, eid: int, choice: str) -> bool:
    """Does this character stand on that leg of its class's fork?

    **Lifted out of `Cast` so the header gate can ask it**, which is the
    whole point. A class feature's options gate themselves on their own leg
    two different ways -- nine of the fourteen with `c.build("f0sN")` in the
    body, and five with `requires=on_leg(...)` in the header -- and six feats
    hand a character another leg's option. With the answer living in two
    places, `c.set_build` could reach the body gate and not the header one,
    so `f1217` and `f2989` would have been handed a row that still refused
    itself and the fault would have looked like the verb not working.

    `content.features.builds.on_leg` and `Cast.build` are both one line over
    this now. Same reason `kinds_of` was lifted, and the same reason
    `c.in_form` delegates here.

    Off `Build.choices`, which chargen writes once, plus anything
    `c.set_build` has laid and minus anything it took away. The displaced
    word has to stop answering: `f2989` replaces one covenant manifestation
    with another and a character on both is wrong in the same way a creature
    with two origins is.
    """
    want = choice.strip().lower()
    added = False
    for eff in world.effects.of(eid):
        # **Searched for, not anchored**, and both halves collected before
        # either is answered -- the same two traps `kinds_of` documents. The
        # label leads with the laying row's ref so `audit._claimed` can
        # credit it (#374), and `build:` is a substring of `unbuild:`.
        #
        # Returning on the first match instead would make the answer depend
        # on effect iteration order the moment one row adds a leg and
        # another takes it away.
        tag = eff.label
        if f"unbuild:{want}" in tag:
            return False
        added = added or f"build:{want}" in tag
    if added:
        return True
    held = world.get(eid, Build)
    return held is not None and want in held.choices


def kinds_of(world: World, eid: int) -> frozenset[str]:
    """A creature's type words: undead, goblin, beast, natural, and so on.

    Lifted out of `Cast` so `dsl.candidates` can ask it. A target line reading
    "each undead creature in the burst" is a restriction on the pool, and while
    this lived on `Cast` the only place to ask it was the body -- which means the
    row was offered against creatures it would then decline.

    Off the stat block's own type line, plus anything `c.set_origin` has written
    on and minus anything that took one away. A character has no type line, and
    nineteen races print a sentence that gives one a word anyway.
    """
    words: set[str] = set()
    gone: set[str] = set()
    for eff in world.effects.of(eid):
        # **Searched for, not anchored.** The label leads with the laying
        # row's ref so that `audit._claimed` can credit it (#374), so the
        # marker is no longer at position zero. `unorigin:` is tested first
        # because `origin:` is a substring of it and splitting on the shorter
        # one would read "natural" out of "unorigin:natural".
        tag = eff.label
        if "unorigin:" in tag:
            gone.add(tag.split("unorigin:", 1)[1])
        elif "origin:" in tag:
            words.add(tag.split("origin:", 1)[1])
    row = stat_block(world, eid)
    if row:
        import json

        words |= set(json.loads(row.get("keywords") or "[]"))
        for column in ("kind", "origin"):
            if row.get(column):
                words.add(row[column])
    elif world.get(eid, Build) is not None:
        # **Every player character is a natural humanoid**, and nothing on
        # any race's page says so -- which is exactly why nothing had it.
        # Camille's ruling, #542: the races that print a type sentence are
        # not the only ones with a type, they are the ones carrying an
        # *additional* one. The compendium omits the universal half because
        # it is the default, so there was never anything to parse and #537's
        # ETL half is withdrawn.
        #
        # Measured before: every character answered `[]` while every monster
        # answered three or four words, so `humanoid` -- the second
        # most-asked type word in the tree, 22 sites -- was False for the
        # whole party. A monster that raises slain humanoids raised nobody,
        # and a target line restricted to humanoids was offered against an
        # empty pool.
        #
        # **Keyed on `Build`, not on the absence of a stat block.** `Build`
        # is added in exactly one place, `chargen.spawn`, and
        # `actions.py:967` and `:1428` already use `world.get(actor, Build)
        # is not None` to mean "is a player character". Keying on the
        # missing stat block instead would also catch the audit dummy, whose
        # `types=` knob depends on having *no* words unless given some --
        # so rows gating on `humanoid` would start passing on the board and
        # the change would hide faults rather than find them.
        #
        # The 19 races whose page names a different origin lay it with
        # `c.set_origin(..., instead_of="natural")`, and the `unorigin:`
        # subtraction below takes `natural` off. An origin is exclusive; a
        # keyword like `undead` or `reptile` is additive and needs no
        # exception here.
        words |= {"natural", "humanoid"}
    # The type line parenthesises its subtypes -- "(undead)" -- and a power
    # asking whether something is undead should not have to know.
    return frozenset(
        word
        for word in (_type_word(w) for w in words)
        if word and word not in gone
    )


def telepathy_of(world: World, eid: int) -> int:
    """How far this creature's telepathy reaches, in squares. 0 for none.

    **A radius, not a sense.** Five rows print it and four use it only to
    measure creatures within it -- "mark each enemy within the range of
    your telepathy", "each ally within your telepathy range". None asks
    whether anything is perceived, so this is deliberately not a
    `Senses`/`has_sense` entry: three further rows mention telepathy as
    *communication* ("communication, not a fight") and want nothing from
    it.

    **Zero is the answer for every creature but two races**, and that has
    to make the readers no-ops rather than board-wide. A missing radius
    must not mark every enemy on the map, which is the direction a `None`
    meaning "unbounded" would fail in. #665.
    """
    from .components import Mods

    held = world.get(eid, Mods)
    if held is None or not held.items:
        return 0
    return max(0, held.total("telepathy", {}))


def sheltered_from(world: World, actor: int, target: int) -> bool:
    """Does this creature have cover or concealment against that one?

    `m3675a2`'s printed target line: "one creature in the burst the m3675
    has concealment or cover against". One reader rather than a `Target`
    field each, because **the two halves are not the same kind of
    question** -- concealment is a property of the creature alone and does
    not vary by who is looking, while cover is traced between two squares.
    So the disjunction cannot be `Target.any_of` over two fields: one of
    them would be constant across the pool, and a field that answers the
    same for every candidate is a Requirement wearing a target line's
    clothes.

    Asked **outward from the actor**, like every relational half of
    `dsl._stands_right`: `cover_between(world, target, actor)` is the cover
    the target faces when shooting back, which is the actor's cover from it.
    Getting that round the wrong way reads as "the target has cover", which
    is a different card. #656.
    """
    return (
        concealment_of(world, actor) is not Cover.NONE
        or cover_between(world, target, actor) is not Cover.NONE
    )


def acting_independently(world: World, eid: int) -> bool:
    """Is this companion acting on its own this round?

    **The state was on the board and a docstring said it was not.** Eight
    ranger feats print "while your beast companion acts independently" and
    all eight were marked for a mode that "does not exist" -- while
    `Companion.commanded` has recorded "the round its owner last spent an
    action on it" since summons were written, and `turns._uncommanded`
    already reads it to run a summon's Instinctive Effect. #661.

    False for anything that is not a companion: a creature taking its own
    turn is not acting independently of anybody.
    """
    from .components import Companion

    mine = world.get(eid, Companion)
    return mine is not None and mine.commanded != world.round


def on_the_ground(world: World, eid: int) -> bool:
    """Is this creature in contact with the floor?

    What five rows' target lines ask: "targets enemies in the burst touching
    the ground", "affects only creatures in contact with the ground", and
    `m5741a5`'s negative, "a nonflying creature's space".

    **Two inputs, and neither alone is the printed test.** `falling.height`
    is the altitude and `falling.airborne` is how the creature is moving
    right now -- a *hovering* creature at height 0 is not touching the
    ground, and a *climbing* one is holding on to a wall, which is why
    `falling.AIRBORNE` counts climbing and says so.

    **Not the content `_airborne` in `level_05/skirmishers.py`**, which asks
    whether the creature *has* a fly speed. That is a different question and
    a deliberate one where it is used -- flight can be taken away, so having
    the mode is the whole of the question for a row about what a creature
    can do. It is the wrong half for a target line about where the creature
    is, and `m216a2` was using it for exactly that. #660.

    Lifted into `query` for the reason `kinds_of` was: while the test lives
    in a body, the only place to ask is the body, so the row is offered
    against creatures it then declines.
    """
    from .falling import airborne, height

    return height(world, eid) == 0 and not airborne(world, eid)


def living(world: World, eid: int) -> bool:
    """Is this a living creature? Ten rows print the word as a restriction.

    **"Living" is not a type word that anything writes down.** Every card
    meaning it is drawing the line against the undead, and every row in the
    tree spells it by hand as `not c.is_kind("undead")` -- so this is that
    read, named once, rather than a new word for anybody to lay.

    The clause it answers is a *target* restriction nine times out of ten --
    "one living creature", "a bloodied, living enemy", "living creatures in
    the burst" -- which is why it belongs here next to `kinds_of` and not on
    `Cast`: `dsl.candidates` has to ask it to narrow the pool, and a row that
    asks in its body has already been offered against creatures it will then
    decline.

    **The both-words case is the whole reason this needs a function.** Two
    races print "you are both living and undead", so they carry *both*
    words, and the plain reading -- undead means not living -- makes them
    neither. `racial._BOTH` records that and both rows dropped their living
    half for it. So `living` is spelled the other way round: the word wins
    where it is present, and its absence only matters when `undead` is
    there to argue with.

    **Constructs are the half a negative set cannot say**, and #411 wrote
    the exact test down before anything could implement it: *"not undead,
    and not construct unless it carries living"*. Twenty-five stat blocks
    carry **both** `living` and `construct` and the cards call them living,
    while a construct with neither word is not -- so `kinds_without={
    "undead"}` admits a non-living construct and `kinds_without={"undead",
    "construct"}` refuses the twenty-five. Seven rows have carried that
    exception as a marker. It is one `if` here, and it was never a field on
    `Target` nor anything `chargen` could store.

    So the word wins where present, and absence is only read against the
    two words that argue with it.

    Before #542 a player character carried no type words at all, so this
    would have answered True for the party by accident rather than on
    purpose -- which is a different thing and would have broken the moment
    anything undead joined it.
    """
    words = kinds_of(world, eid)
    if "living" in words:
        return True
    return "undead" not in words and "construct" not in words


def taking_ongoing(
    world: World, eid: int, types: frozenset[DamageType] = frozenset()
) -> bool:
    """Is this creature burning? Of any of `types`, or of any type at all.

    `Effect.ongoing` is an `(amount, dtype)` pair, so the question was already
    answerable and had no reader -- which meant a target line reading "one
    creature taking ongoing poison damage" had to be asked in the body, after
    the row had been offered against creatures it would decline.

    **The type is not optional for most of them.** Seven of the eight rows that
    wanted this name a damage type and one does not, so a bare "is it burning"
    would accept a creature alight from the wrong source in seven cases out of
    eight.
    """
    for eff in world.effects.of(eid):
        burn = getattr(eff, "ongoing", None)
        if not burn:
            continue
        amount, dtype = burn
        if amount and (not types or dtype in types):
            return True
    return False


def is_trap(world: World, eid: int) -> bool:
    from .components import Trap

    return world.get(eid, Trap) is not None


def is_conjuration(world: World, eid: int) -> bool:
    from .components import Conjuration

    return world.get(eid, Conjuration) is not None


def can_act(world: World, eid: int, *, ignoring: Condition | None = None) -> bool:
    # A trap and a conjuration have no hit points to be unconscious about.
    # Without this they failed `conscious` and could never make the attack
    # they exist to make.
    if is_trap(world, eid) or is_conjuration(world, eid):
        return True
    held = [c for c in active(world, eid) if c is not ignoring]
    return conscious(world, eid) and not any(rules(c).cannot_act for c in held)


def can_react(world: World, eid: int, *, ignoring: Condition | None = None) -> bool:
    """Can this creature spend an immediate action?

    `ignoring` waives **one** condition, and exists for one printed shape:
    a row whose trigger is being affected by a condition, answering with
    an immediate interrupt that shrugs it off. `Effects.apply` installs
    the condition before announcing it -- deliberately, because announcing
    first let a listener end the effect while its modifiers were still
    unattached and leave them on the creature forever -- so by the time
    the row is offered, the creature already has the thing it exists to
    remove. Dazed and stunned both stop you reacting, which are exactly
    the two conditions such a line is printed for.

    One condition, not a general waiver: a creature stunned a round ago
    still cannot answer, and should not.
    """
    return can_act(world, eid, ignoring=ignoring) and not any(
        rules(c).no_reactions for c in active(world, eid) if c is not ignoring
    )


def in_form(world: World, eid: int, *names: str) -> bool:
    """Is this creature in one of the named forms?

    "Requirement: it must be in beast or hybrid form" is 58 rows across the
    tree, and the words are the 4e categories -- `humanoid`, `beast`,
    `hybrid` -- rather than the species the card prints, because a species is
    a printed name and `races/` already holds refs for that reason.

    **Permissive when nothing has been recorded**, which is not a shortcut:
    the convention is `_in_shapes`' and its note states the reasoning -- a
    creature that has not changed shape is in whatever shape it was found in,
    the stat block does not say which, so no attack is ruled out. Guessing a
    starting form instead would silently refuse half of a shapechanger's
    card on the strength of something nobody printed.

    With no names it answers whether the creature is in *any* recorded form,
    which is the other side of the same question -- see `shifted`.
    """
    held = world.get(eid, Shapes)
    live = held.live if held is not None else set()
    if not live:
        return True
    wanted = {n.strip().lower() for n in names if n.strip()}
    return bool(live & wanted) if wanted else True


def shaped(world: World, eid: int) -> bool:
    """Has this creature taken a shape that is not its own?

    "A +1 bonus to all defences against creatures not in their natural form"
    asks this, and it is the complement of `in_form` rather than a call to it
    with no arguments: that one is permissive about an unrecorded shape
    because a Requirement should not refuse an attack, where this one has to
    answer *no* for a creature nobody has transformed.

    **Named `shaped` after `Condition.SHAPED`, which is the convention**, and
    renamed from `shifted` because that was a false friend of `c.shift` --
    they sat on consecutive lines of an alphabetical dump, so `if
    c.shifted():` after a `c.shift(2)` read as the obvious way to ask whether
    the step happened and was always False unless the creature was
    polymorphed. No row ever called it, which is the only reason the rename
    costs nothing. #595.
    """
    held = world.get(eid, Shapes)
    return bool(held is not None and held.live)


def takes_half(
    world: World,
    eid: int,
    dtypes: frozenset[DamageType] = frozenset(),
    ctx: dict[str, Any] | None = None,
) -> bool:
    """Insubstantial: everything that reaches this creature is halved.

    `dtypes` is the whole type of the blow being asked about, and the answer
    is False when the trait excepts any of them -- "takes half damage from
    any damage source, **except those that deal force damage**", which six
    stat blocks print and `Rules.insubstantial` is a bool and cannot say.

    **The exception is read off the creature**, from `Defences.half_except`,
    not off the effect that laid the trait. That would be wrong if a creature
    ever held two insubstantial traits with different exceptions, and no
    printed block does -- so the simplification costs nothing and keeps this
    a question the damage path can ask with what it already has in hand.

    Called with no `dtypes` it answers the old question, which is what every
    caller asking about the creature rather than a blow wants.

    **`ctx` is for a trait scoped to one attacker** -- `Defences.half_when`,
    #747. **Any** source applying is enough: `half_always` counts the
    ungated ones and each gate is asked about this blow. Reading an empty
    gate list as "unconditional" instead was the first draft's mistake and
    got the common case backwards -- a creature with a gated trait has a
    non-empty list, and an ungated trait laid beside it left no mark, so the
    gate silently suppressed it.

    **A caller with no blow in hand needs no special case.** The drivers
    suite and the policy readers ask `takes_half(world, eid)`, and handing
    the predicate `{}` makes a gate that reads `ctx["source"]` answer False
    -- the conservative answer to "is this creature hard to hurt" asked in
    the abstract, and the one that keeps a gated trait from reading as a
    blanket one.
    """
    if not any(rules(c).insubstantial for c in active(world, eid)):
        return False
    held = world.get(eid, Defences)
    if held is not None and (held.half_when or held.half_always):
        applies = held.half_always > 0 or any(
            gate(ctx or {}) for gate in list(held.half_when)
        )
        if not applies:
            return False
    if held is None or not held.half_except:
        return True
    # "Except those that deal force damage" excepts the *source*, not the
    # part: a blow that is half force and half cold is one damage source
    # dealing force damage, so none of it is halved.
    return not (set(dtypes) & held.half_except.keys())


def can_shift(world: World, eid: int) -> bool:
    """A shift is barred separately from a walk, and by different powers."""
    return can_move(world, eid) and not any(rules(c).no_shift for c in active(world, eid))


def can_move(world: World, eid: int) -> bool:
    return can_act(world, eid) and not any(rules(c).cannot_move for c in active(world, eid))


def can_walk(world: World, eid: int) -> bool:
    """"It cannot use move actions to walk or run", but it may still shift.

    The exact mirror of `c.cannot_shift`, and neither condition says it:
    `immobilized` bars the shift as well, which is a stronger card than the
    rows printing this one. Held as a modifier rather than a condition
    because nothing else about the creature changes -- it is not slowed, it
    grants nothing, it is simply not going anywhere on its feet.
    """
    if not can_move(world, eid):
        return False
    mods = world.get(eid, Mods)
    return not (mods is not None and mods.items and mods.total("no_walk", {}) > 0)


def can_run(world: World, eid: int) -> bool:
    """"It cannot run", with the walk left alone.

    The run-only mirror of `can_walk`, and the reason it is a separate
    reader rather than a flag inside that one: `c.no_walk` is documented
    as *"it cannot use move actions to walk **or** run"*, so the only
    prohibition this engine had took both. `m5452a2`'s whole card is a
    move action spelled out -- it walks its speed and cannot run -- so
    taking the walk away is not an option there. The walk **is** the row.

    Refuses whatever `can_walk` refuses, because a creature that cannot
    walk cannot run either; `no_run` is the extra bar on top. The same
    relationship `c.cannot_shift` has to `c.no_walk`, and this file's own
    note on that pair gives the reason it matters: *"a row printing only
    one half was being written as the stronger card or dropped"*, which is
    exactly what had happened. #670.
    """
    if not can_walk(world, eid):
        return False
    mods = world.get(eid, Mods)
    return not (mods is not None and mods.items and mods.total("no_run", {}) > 0)


# -- combat advantage -------------------------------------------------------


def grants_ca(world: World, eid: int) -> bool:
    """True when the creature grants combat advantage to everyone."""
    return any(rules_for(world, eid, c).grants_ca for c in active(world, eid))


def can_flank(world: World, eid: int) -> bool:
    """May this companion stand in the far square and count?

    No, by default, and `allies` leaves companions out for exactly that
    reason: a spirit standing in the right place is furniture. "Your
    familiar can flank with you or your allies" is the printed line that
    turns one on, and `c.can_flank` lays the modifier read here.
    """
    mods = world.get(eid, Mods)
    return mods is not None and bool(mods.items) and mods.total("can_flank") > 0


def flankers(world: World, eid: int) -> list[int]:
    """Who may hold the other side of a creature for `eid`.

    Its allies, plus any companion told it can flank. `allies` excludes
    companions on purpose -- "each ally adjacent to your spirit companion"
    must not mean the spirit -- so the exception is made here instead of
    widening that default.
    """
    return [
        o
        for o in allies(world, eid, companions=True)
        if world.get(o, Companion) is None or can_flank(world, o)
    ]


def flanked_by(world: World, target: int, attacker: int) -> bool:
    """Is `target` flanked by `attacker` and one of its allies?

    Both flankers must be able to attack -- a stunned ally standing in the
    right square is furniture, and the printed rule says so.
    """
    if not adjacent(world, attacker, target) or not can_act(world, attacker):
        return False
    space = squares(world, target)
    for mate in flankers(world, attacker):
        if mate == target or not can_act(world, mate) or not adjacent(world, mate, target):
            continue
        for a in squares(world, attacker):
            for b in squares(world, mate):
                if world.grid.flanks(a, b, space):
                    return True
    return False


#: Pairs whose combat advantage is being resolved right now.
#:
#: `has_combat_advantage` reads a `gains_ca_when` modifier, so a row printing
#: "gains combat advantage while an ally has it" asks this function again from
#: inside its own gate -- and two creatures each carrying that clause is a
#: cycle, not deep recursion. Reproduced with two copies of one level-10
#: creature and a single call: `RecursionError`.
#:
#: **False for a pair already in flight is the right answer, not merely the
#: safe one.** "An ally has combat advantage" means independently of me; a
#: cycle has no independent answer, so there is nothing truthful to return.
#:
#: Lived in `content/monsters/level_10/soldiers_sa.py` as a local
#: `_RESOLVING_CA` -- the right call for a content wave, but it guarded two
#: rows and the next row of the shape would crash again. #376.
_IN_FLIGHT: set[tuple[int, int]] = set()


def has_combat_advantage(
    world: World, attacker: int, target: int, power: str = ""
) -> bool:
    if (attacker, target) in _IN_FLIGHT:
        return False
    _IN_FLIGHT.add((attacker, target))
    try:
        return _has_combat_advantage(world, attacker, target, power)
    finally:
        _IN_FLIGHT.discard((attacker, target))


def _has_combat_advantage(
    world: World, attacker: int, target: int, power: str = ""
) -> bool:
    # "You do not grant combat advantage to any of your enemies" suppresses
    # every route at once, so it is asked first -- unlike `unflankable`
    # below, which is one branch and lets a hidden or granting attacker
    # through. Four rows across runepriest, swordmage and battlemind print
    # the wider sentence, and each was left out because the +2 is computed
    # here from the board and no modifier could reach it.
    # The pair is handed to the gate. Both of these were read with an empty
    # context, so `c.no_advantage(when=...)` and `c.cannot_be_flanked(when=)`
    # would have been silently false -- and the printed lines are narrow:
    # "you do not grant combat advantage to *those* creatures", "unless both
    # of you are flanked". Without the names there is nothing to ask about.
    # **`power` is here because fifteen rows narrow by it** -- "with your cold
    # powers", "for close blast powers" -- and without it those gates could only
    # ever have been silently true. Empty for the callers that are asking about a
    # pair of creatures rather than about a swing, which is most of the sixty-odd
    # of them, and a gate wanting a keyword is then correctly False: nothing can
    # claim a power's narrowing when no power has been named.
    ca_ctx = {"attacker": attacker, "target": target, "power": power}
    denied = world.get(target, Mods)
    if denied is not None and denied.items and denied.total("no_advantage", ca_ctx) > 0:
        return False
    if grants_ca(world, target):
        return True
    if world.relations.holds(Relation.GRANTS_CA_TO, target, attacker):
        return True
    # The gated form of the same sentence. `c.grants_advantage(when=)` cannot use the
    # relation above, because a relation carries no predicate and this function returns
    # as soon as it holds -- so the conditional version lays a modifier instead and is
    # read here, with the same `ca_ctx` the two suppressing keys already get.
    granting = world.get(target, Mods)
    if granting is not None and granting.items \
            and granting.total("grants_ca_to", ca_ctx) > 0:
        return True
    # **The same sentence from the attacker's side, which the three routes above
    # cannot say.** All of them live on the *target*, so "this creature grants
    # combat advantage" is sayable and "I gain combat advantage against anything
    # immobilized" is not -- there is no creature to lay it on, the set is
    # whatever happens to be immobilized at the moment of the swing. Fifteen rows
    # print the second shape and each was waiting on a verb; `c.gains_advantage`
    # lays this and it is read here with the same context.
    gaining = world.get(attacker, Mods)
    if gaining is not None and gaining.items \
            and gaining.total("gains_ca_when", ca_ctx) > 0:
        return True
    if unseen_by(world, target, attacker):
        return True
    # "Enemies cannot gain combat advantage by flanking it" is a printed
    # trait and there was no way to suppress this one branch -- the whole
    # question was answered from the board with nothing on the creature
    # able to speak to it.
    mods = world.get(target, Mods)
    if mods is not None and mods.items and mods.total("unflankable", ca_ctx) > 0:
        return False
    return flanked_by(world, target, attacker)


def hidden_from(world: World, eid: int) -> set[int]:
    """Who cannot see this creature."""
    return {
        w
        for w in world.relations.targets(Relation.HIDDEN_FROM, eid)
        if not sees_through(world, w, eid)
    }


def granted_actions(world: World, eid: int) -> dict[tuple[str, str], int]:
    """Things this creature may do for a different action than usual.

    Keyed `(what, cost)` -- `("shift", "minor")` -- with the value being how
    far, where that means anything. A stance reading "you can shift 2
    squares as a move action" changes the menu rather than doing anything,
    and `actions.legal` builds that menu from the rules alone: a shift was
    one square for a move action, full stop, so the whole family of rows
    granting a cheaper or longer one had nowhere to be written.
    """
    mods = world.get(eid, Mods)
    if mods is None or not mods.items:
        return {}
    out: dict[tuple[str, str], int] = {}
    for m in mods.items:
        what, sep, cost = m.what.partition(" as ")
        if not sep:
            continue
        n = mods.total(m.what, {})
        if n > 0:
            out[(what, cost)] = max(out.get((what, cost), 0), n)
    return out


def immune_to(
    world: World,
    eid: int,
    cond: Condition,
    source: int | None = None,
    power: str = "",
) -> bool:
    """Can this condition not be laid on this creature at all?

    Distinct from curing one: "you cannot be marked or slowed until the end
    of your next turn" is a window in which the condition never arrives,
    and stripping it afterwards is a different sentence that leaves every
    rider hung on `ConditionApplied` already paid out.
    """
    mods = world.get(eid, Mods)
    if mods is None or not mods.items:
        return False
    # **The context, which used to be `{}`.** `Mods.total` evaluates a modifier's
    # gate through `applies(ctx)`, so an empty dict let a gated immunity be written
    # and then asked a question it could not answer. Keys follow the convention in
    # `escape` and `skills`: the participants by name, plus what is being resisted.
    #
    # **`power` is the row doing the laying**, which the context carried the
    # creature instead of -- so "immune to slow and immobilize caused by cold
    # powers" could not be written while `c.immune(when=)` happily accepted it.
    # The ref rather than the keywords, the way `no_provoke` passes `ctx["why"]`:
    # a gate asks `Keyword.COLD in get(ctx["power"]).keywords` and the keyword
    # list stays where it lives. **A monster ability answers that too** -- a
    # stat block's ability is an ordinary declared row with its own keywords, so
    # "caused by a cold power" covers a monster's cold breath and a wizard's
    # spell alike, which is what the printed word means.
    #
    # Empty, not None, for a condition arriving from no row -- a failed save, a
    # trap, a zone's own clause -- matching how the damage context settled on
    # `source` plus `from_attack` rather than a nullable attacker (#302). A
    # keyword gate is then correctly False: nothing can claim a power's
    # narrowing when no power has been named.
    ctx = {"cond": cond.value, "target": eid, "source": source, "power": power}
    return mods.total(f"immune to {cond.value}", ctx) > 0


def holds_somebody(world: World, eid: int) -> bool:
    """Is this creature holding anyone in a grab? "Requirement: you must
    have a creature grabbed."

    **A `requires=` gate is called as `(world, actor)`**, before there is a
    `Cast` at all -- `dsl.can_branch` invokes it straight from `usable` -- so
    the three readers on `Cast` were all unreachable from a Requirement. The
    only `(world, eid)` form in the tree lived in
    `content/powers/fighter/holds.py`, which meant monster files imported from
    a fighter power file to ask this. #362.

    Two agents and I guessed three different wrong modules for it in one
    afternoon (`engine.query`, `components.Relation`, `engine.types`), which is
    the argument for it living in the module whose whole job is
    `(world, ...)` questions.
    """
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def held_by(world: World, eid: int) -> list[int]:
    """Everyone holding this creature in a grab. `holds_somebody`'s mirror.

    `Cast.grabbed_by` delegates here so there is one implementation, and a
    `requires=` gate can ask the question without a `Cast`.
    """
    from .escape import holders

    return holders(world, eid)


def sees_invisible(world: World, eid: int) -> bool:
    """Does this creature see what is hidden from everybody else?

    A modifier rather than a condition, because it is granted for a
    duration by a power and nothing about the creature itself changes.
    """
    mods = world.get(eid, Mods)
    return mods is not None and bool(mods.items) and mods.total("see_invisible", {}) > 0


def sees_through(world: World, watcher: int, who: int) -> bool:
    """Can this watcher see that creature whatever it is hiding behind?

    `sees_invisible` is the unlimited answer and was the only one, so
    "truesight 5" and "that creature cannot become invisible to you" -- a
    radius and a named creature -- had nothing to be written as. Both are
    modifiers rather than conditions for the same reason `see_invisible` is.
    """
    if sees_invisible(world, watcher):
        return True
    mods = world.get(watcher, Mods)
    if mods is None or not mods.items:
        return False
    if mods.total(f"truesight:{who}", {}) > 0:
        return True
    reach = mods.total("truesight", {})
    return reach > 0 and distance_between(world, watcher, who) <= reach


def sight_capped(world: World, watcher: int, who: int) -> bool:
    """Is that creature simply too far off for this watcher to see?

    "The target does not have line of sight to any creature more than 3
    squares away from it" is a cap on sight rather than the loss of it, so
    `Condition.BLINDED` says something else and nothing else came close.
    """
    mods = world.get(watcher, Mods)
    if mods is None or not mods.items:
        return False
    cap = mods.total("sight_range", {})
    return cap > 0 and distance_between(world, watcher, who) > cap


def blinded(world: World, eid: int) -> bool:
    """Can this creature see at all?

    **The reader `Rules.blind` never had.** `conditions.py` declares the flag and
    sets it for `Condition.BLINDED`, and nothing in the engine consulted it -- so
    a blinded creature granted combat advantage and took its -2, because those
    two have readers, and could still see perfectly well. Every sight question in
    the tree answered as though it were not blind.

    Read off the flag rather than testing `Condition.BLINDED` directly, so that a
    second condition meaning "cannot see" only has to say so in `RULES`. #406.
    """
    return any(rules(c).blind for c in active(world, eid))


def unseen_by(world: World, watcher: int, who: int) -> bool:
    """Is `who` invisible to `watcher`?

    The relation alone was the whole answer, so "you can see invisible
    creatures" -- printed by two classes and every darkvision-adjacent
    monster trait -- had nothing to switch off. Asked here rather than at
    each of the two places that read `HIDDEN_FROM`, so the sight and the
    combat advantage can never disagree.

    **Blindness is asked first and answers everything.** A creature that cannot
    see does not see anybody, hidden or not, and `sight_capped`'s docstring said
    as much while pointing elsewhere: "a cap on sight rather than the loss of it,
    so `Condition.BLINDED` says something else". That something else was nowhere
    until #406.
    """
    if blinded(world, watcher):
        return True
    if sight_capped(world, watcher, who):
        return True
    if revealed(world, who):
        return False
    return world.relations.holds(Relation.HIDDEN_FROM, who, watcher) and not sees_through(
        world, watcher, who
    )


def revealed(world: World, who: int) -> bool:
    """Has this creature been stripped of the benefit of invisibility? #774.

    **The target's side of the waiver, where `sees_through` is the
    watcher's.** Two monster rows print "the target cannot benefit from
    invisibility or concealment" -- the concealment half is `c.no_cover`,
    and the invisibility half had nowhere to be written, because the only
    waiver was on whoever was looking. A row printing the second cannot be
    written as the first: giving the caster see-invisible lets it see *every*
    hidden creature, which is a much bigger rule than the card.

    Held as a labelled effect rather than a `Mods` key, because `unseen_by`
    is asked with no attack context and `Mods.total` wants one -- the same
    reason `c.set_origin` and `c.deals` hold their words this way.
    """
    return any(" revealed" in eff.label for eff in world.effects.of(who))


def concealment_of(
    world: World, target: int, ctx: dict[str, Any] | None = None
) -> Cover:
    """How hard this creature is to see, as an attack penalty.

    Cover is a fact about two positions and is traced. Concealment is a
    fact about the creature -- dim light, a blur, a cloak of shadow -- so
    it is a modifier it carries, and nothing read one until now. Seven
    classes print "you gain concealment" and every one of those rows was
    left out of the tree for want of this.

    `PARTIAL` is the ordinary case at -2; `SUPERIOR` is total concealment
    at -5, which is what `c.conceal(total=True)` sets.
    """
    mods = world.get(target, Mods)
    if mods is None or not mods.items:
        return Cover.NONE
    # The attack context, not `{}`. A gate reading a key the context does
    # not carry is silently false, so "partial concealment from creatures
    # more than 3 squares away" -- which is how several creatures print it
    # -- could not be written as concealment at all, and was hand-rolled as
    # a bare bonus to defences that wrongly stacked with cover.
    n = mods.total("concealment", ctx or {})
    if n >= int(Cover.SUPERIOR):
        return Cover.SUPERIOR
    return Cover.PARTIAL if n > 0 else Cover.NONE


def light_level(
    world: World, square: Square, dark_zones: list[Any] | None = None
) -> Light:
    """How well lit this square is.

    Two sources, worst wins: the terrain map (`Grid.light`) and any zone
    standing over the square that darkens it. A zone is checked because
    darkness is overwhelmingly *laid* rather than built into a board -- the
    rows asking for this are powers that put out the lights.

    Bright everywhere by default, so a board that never mentions light
    answers `BRIGHT` for every square and the attack path's light term is a
    no-op. 13 rows wait on this; it is the model the other seven light
    symbols are written against.

    **This does not read `Zone.obscured_for`**, and the asymmetry is
    deliberate. A directional obscurity is a fact about who is *looking*,
    and this function is handed a square and no looker -- so it answers the
    square's own grade, which is the conservative answer and the one the
    content readers want ("teleport me somewhere dim" is about the square,
    not about an onlooker). `light_concealment` has the attacker and asks
    `Zones.obscuring_for` for a scan already filtered to that looker.
    """
    worst = Light(world.grid.light.get(square, Light.BRIGHT))
    # `dark_zones` is the caller's own scan, passed in so a loop over the
    # target's squares does not re-walk every zone on the board for each one.
    if dark_zones is None:
        dark_zones = world.zones.dark()
    for zone in dark_zones:
        if square in zone.squares:
            level = Light(zone.obscured)
            if _DARKER[level] > _DARKER[worst]:
                worst = level
    if worst is Light.BRIGHT:
        # **Still has to ask about a carried dimmer**, which is the one
        # thing that can make a bright square darker. The early return was
        # right while `c.light` was the only carried radius -- a light can
        # only brighten, so a square already bright had nothing to gain --
        # and `c.dim` is the opposite operation, so skipping the search left
        # every dimmer invisible on exactly the boards it is for. Caught by
        # `drivers.light_and_dim`'s first assertion. #687.
        return _dimmed(world, square)
    # **A carried light moves, so it cannot be written into the terrain.**
    # `c.light(n)` lays a radius on the creature and this is what reads it:
    # anything within that radius is bright however dark the square itself
    # is. Written as a search over carriers rather than a grid write because
    # the alternative is repainting the map on every step, which is the bug
    # `Zones.refresh` exists to avoid for the same reason.
    for eid, mods in world.each(Mods):
        if not mods.items:
            continue
        radius = mods.total("light_radius", {})
        if radius <= 0:
            continue
        for mine in squares(world, eid):
            if abs(mine[0] - square[0]) <= radius and abs(mine[1] - square[1]) <= radius:
                worst = Light.BRIGHT
                break
        else:
            continue
        break
    return _dimmed(world, square) if worst is Light.BRIGHT else worst


def _anyone_dimming(world: World) -> bool:
    """Is anybody on the board carrying a dimmer at all?

    The cheap half of the question `_dimmed` answers precisely, for
    `light_concealment`'s fast path. See the note there for why a dimmer
    cannot be skipped where a carried light can.
    """
    return any(
        m.what == "dim_radius"
        for _, mods in world.each(Mods)
        for m in mods.items
    )


def _dimmed(world: World, square: Square) -> Light:
    """`BRIGHT`, unless somebody standing near is carrying a dimmer.

    **Read after everything that brightens, and able to beat it.** Five rows
    shed *dim* light rather than bright, and one says outright what the
    order has to be: "this candle sheds dim light in a 2-square radius …
    **bright light within the candle's radius is reduced to dim light**". So
    a dimmer lowers bright to dim and never lightens a square that is
    already darker -- it is a reduction, not a level, which is why it cannot
    be `c.light` with a sign.

    `c.light` could not say this: it makes anything inside its radius bright
    "however dark the square itself is", the opposite operation, and the
    reason five rows sat `out_of_combat` on "light is not modelled" after
    the model landed (#686). #687.
    """
    for eid, mods in world.each(Mods):
        if not mods.items:
            continue
        shade = mods.total("dim_radius", {})
        if shade <= 0:
            continue
        for mine in squares(world, eid):
            if (abs(mine[0] - square[0]) <= shade
                    and abs(mine[1] - square[1]) <= shade):
                return Light.DIM
    return Light.BRIGHT


#: A sense with no printed range. The board is never more than a few dozen
#: squares across, so any number past it is "everywhere" -- and a sentinel is
#: better than `None` here because the value is summed through `Mods.total`
#: like every other modifier, and `None` would have to be special-cased at
#: every read.
UNLIMITED_SENSE = 100


#: The order the levels compare in. `Light` is a `StrEnum`, so `<` on it is
#: alphabetical -- "bright" < "dark" < "dim" -- which is wrong twice over.
_DARKER = {Light.BRIGHT: 0, Light.DIM: 1, Light.DARK: 2}


def sees_in(world: World, eid: int, level: Light, distance: int = 0) -> bool:
    """Can this creature see normally at that light level?

    The senses are `Mods` keys rather than components, for the reason every
    other standing modifier is: they are granted for an encounter by a row
    and have to come off when it ends.

    * `darkvision` -- darkness is bright. Covers dim light too, which is why
      it is tested first: a creature that sees in the dark is not inconvenienced
      by shade.
    * `low_light` -- dim light is bright, darkness is not.
    * `blindsight` and `tremorsense` -- light is irrelevant entirely. They are
      separate keys because the printed ranges differ and a row may grant one
      without the other, and both answer True here.
    """
    if level is Light.BRIGHT:
        return True
    mods = world.get(eid, Mods)
    if mods is None or not mods.items:
        return False

    def reaches(key: str) -> bool:
        """Does this sense answer, and does it reach that far?

        The printed range is the modifier's value and `0` means the sense is
        absent. `UNLIMITED_SENSE` is what the verbs store when the card
        prints no range, so the comparison needs no second branch.
        """
        radius = mods.total(key, {})
        return radius > 0 and radius >= distance

    if reaches("blindsight") or reaches("tremorsense") or reaches("darkvision"):
        return True
    return level is Light.DIM and reaches("low_light")


def has_sense(world: World, eid: int, sense: str) -> bool:
    """Does this creature have that named sense at all?

    `sees_in` answers the question the attack path asks -- *can you see at
    this level, this far* -- and three rows ask a different one: whether a
    creature **has** a sense, as a fact about it. "If the creature has
    darkvision, the penalty applies to all its attacks"; "creatures without
    darkvision are blinded while in the area"; "gains any blindsight or
    darkvision of an allied creature within 5 squares".

    So this is the per-key public reader `Mods` did not expose, and writing
    those three rows without it means guessing. One of them was written as a
    guess first and `audit` caught it firing 48 times and doing nothing.

    `sense` is the modifier key: `"darkvision"`, `"low_light"`,
    `"blindsight"`, `"tremorsense"`.
    """
    mods = world.get(eid, Mods)
    return bool(mods is not None and mods.items and mods.total(sense, {}) > 0)


def light_concealment(world: World, attacker: int, target: int) -> Cover:
    """The concealment the target gets from standing somewhere badly lit.

    **Kept apart from `concealment_of` on purpose.** That one answers "what
    is this creature carrying", is called from thirty-odd content rows with
    only a target, and 60 of those calls would have had to change to pass an
    attacker. Light is a fact about a square *and* about who is looking --
    darkness conceals from me and not from the creature with darkvision --
    so it cannot be a modifier the target carries.

    `resolve.attack_mods` takes the larger of this, cover and carried
    concealment, which is the printed rule that they do not add.
    """
    # **The bright-board fast path, and it is not an optimisation to taste.**
    # This runs on *every attack*, and the first version walked the zone list
    # once per square of the target before concluding that a board nobody has
    # darkened is bright. Measured: the wide audit went from ~43 minutes to a
    # projected ~73. So the cheapest question is asked first -- is there any
    # light on this board at all -- and on every board that never mentions
    # light the answer is no and nothing else is read.
    # **A carried dimmer is the third source and cannot be skipped**, which
    # is the asymmetry with `c.light`: a carried *light* only ever removes
    # concealment, so on a board the fast path calls bright there was none
    # to remove and skipping the carrier walk is free. A carried *dimmer*
    # creates concealment, so a board with nothing painted and no zone can
    # still conceal somebody. `drivers.light_and_dim` caught this with the
    # assertion that matters -- the level went dim and the attack penalty
    # stayed zero. #687.
    #
    # Scanned by key rather than through `Mods.total`: no gating, no
    # stacking arithmetic, just "does anybody carry one". That is a flat
    # pass over about ten creatures, where the thing this fast path exists
    # to avoid was walking the *zone list once per square of the target*.
    if (not world.grid.light and not world.zones.darkening
            and not _anyone_dimming(world)):
        return Cover.NONE
    # **Filtered by who is looking**, which is the one place that can be
    # done: this function has the attacker and `light_level` does not. Four
    # rows print an obscurity with a side, and a zone whose side excludes
    # this attacker is simply not in the scan -- so the whole chain below
    # reads as if it were not there, rather than every reader learning
    # about directions.
    dark_zones = world.zones.obscuring_for(attacker)

    # The distance matters: a sense with a printed range stops answering past
    # it, which is the whole of what the range is for.
    far = distance_between(world, attacker, target)
    if sees_in(world, attacker, Light.DARK, far):
        return Cover.NONE
    worst = Light.BRIGHT
    for square in squares(world, target):
        level = light_level(world, square, dark_zones)
        if _DARKER[level] > _DARKER[worst]:
            worst = level
    if sees_in(world, attacker, worst, far):
        return Cover.NONE
    if worst is Light.DARK:
        return Cover.SUPERIOR
    return Cover.PARTIAL if worst is Light.DIM else Cover.NONE


def cover_waived(
    world: World, attacker: int, target: int, ctx: dict[str, Any] | None = None
) -> int:
    """How much cover and concealment this pairing simply does not count.

    Two printed sentences meet here and they are aimed at opposite ends of
    the attack: "you ignore cover and concealment" sits on the attacker,
    "the target does not benefit from cover against you" sits on the
    target. `resolve.attack` took an `ignore_cover` argument and nothing
    else, so both could only be said for the length of one `c.strike`.

    The larger of the two answers, not their sum, because each is a
    statement about the same penalty. `Cover.PARTIAL` waives the ordinary
    -2 and leaves superior cover standing, which is what "partial cover or
    partial concealment" prints.

    **This is the waiver for cover specifically.** Four rows print sight
    that passes concealment and *not* cover -- "sees a wounded creature
    however well hidden" -- and `concealment_waived` is that one. Reading
    one number for both is what made those four unwritable: laying the
    broad waiver would let the creature shoot through a wall for free,
    which `m5426a0`'s note calls "a bigger rule than the card".
    """
    ctx = ctx or {}
    mine = world.get(attacker, Mods)
    theirs = world.get(target, Mods)
    return max(
        mine.total("ignore_cover", ctx) if mine is not None and mine.items else 0,
        theirs.total("no_cover", ctx) if theirs is not None and theirs.items else 0,
    )


def concealment_waived(
    world: World, attacker: int, target: int, ctx: dict[str, Any] | None = None
) -> int:
    """How much **concealment** this pairing does not count. #771.

    Everything `cover_waived` answers, because "you ignore cover and
    concealment" covers this half too -- plus the narrower sentence that
    only exists here: `c.ignore_cover(concealment_only=True)`, which is
    four monster and feat rows whose sight passes a fog bank and stops at a
    wall.

    So the two readers are deliberately **nested, not parallel**: anything
    waiving cover waives concealment, and not the reverse. Written the
    other way round, a creature printed as seeing through concealment
    would have been handed cover too.
    """
    ctx = ctx or {}
    mine = world.get(attacker, Mods)
    narrow = (
        mine.total("ignore_concealment", ctx)
        if mine is not None and mine.items
        else 0
    )
    return max(cover_waived(world, attacker, target, ctx), narrow)


def kind_waived(
    world: World, asker: int, target: int, word: str, ref: str = ""
) -> bool:
    """Does `asker` get to treat `target` as `word` although it is not?

    *"When you use a divine power that normally targets undead, you can also
    target creatures of the elemental origin."* The restriction is checked
    against the **target's** type words; the permission to widen it belongs
    to the **attacker**. So this is the one reader where the waiver is laid
    on one creature and asked about another, and getting that round the
    wrong way makes the feat widen what can be aimed *at its owner*.

    Laid by `c.counts_as(word, kind=...)`, which carries an optional
    `keyword=` for the commonest form of the sentence -- "a *divine* power"
    -- read off the row now running rather than the waiver. `dsl.keywords_of`
    is used and not the header, so a power *granted* the keyword counts, which
    is the more faithful reading of "a divine power".

    **Only the body gate needs this, measured.** Two rows in the corpus
    restrict their printed *target line* to undead and both are monster
    abilities with no divine keyword, so no waiver can ever reach
    `dsl._stands_right`. Every divine row that restricts to undead does it
    in its body through `Cast.is_kind` -- twelve of them -- which is why this
    is read there and `dsl` is left alone. Widen the measurement before
    adding a second reader.
    """
    wanted = word.lower()
    carried: frozenset[str] | None = None

    for eff in world.effects.of(asker):
        tag = eff.label
        if "kindwaiver:" not in tag:
            continue
        spec = tag.split("kindwaiver:", 1)[1].split(" ", 1)[0]
        asked, _, rest = spec.partition(">")
        also, _, needs = rest.partition(":")
        if asked.lower() != wanted:
            continue
        if needs:
            if not ref:
                continue
            if carried is None:
                # **`dsl.keywords_of`, never `Power.keywords`.** Its own
                # docstring is the reason: 12 feats grant a row a keyword for
                # one character, which header data cannot say, and a grant
                # honoured at 21 of 22 readers is this component's commonest
                # bug. Resolved once per call rather than per waiver.
                from .dsl import get, keywords_of

                carried = frozenset(
                    str(getattr(k, "value", k)).lower()
                    for k in keywords_of(world, asker, get(ref))
                )
            if needs.lower() not in carried:
                continue
        if also.lower() in kinds_of(world, target):
            return True
    return False


def cover_between(
    world: World, attacker: int, target: int, *, ranged: bool = False,
    ctx: dict | None = None,
) -> Cover:
    """The worst cover the target has, measured from the attacker's best square.

    Worked out at the moment of the attack by tracing corner to corner --
    `Grid.cover` does the drawing -- rather than stored anywhere, because
    cover is a fact about two positions and both of them move.

    **Terrain always blocks. Creatures block only a ranged attack, and only
    the target's own allies do.** Both halves of that were wrong: every
    creature on the board was counted, for every kind of attack, so a
    fighter in a melee got a cover penalty for the enemy standing beside its
    target, and the target's enemies were sheltering it from its friends.
    Somebody in your way is cover your side gave you.

    **`ctx` is the attack, and it reaches only the carried half.** The trace
    needs no context -- it is two positions -- but a *carried* `"cover"`
    modifier can be gated, and until this parameter existed the gate was
    handed `{}` and read false. `concealment_of` has taken the context from
    the start and sits one line below this call in `resolve.attack`, so the
    asymmetry was the bug rather than a design: `c.conceal(when=)` could say
    "concealment from creatures more than 3 squares away" and
    `c.cover(when=)` could not say "cover against ranged attacks". Four rows
    print the second. #644.

    Callers with no attack in hand pass nothing and get today's behaviour: a
    gated carried modifier reads false, so it is not counted. That
    under-offers rather than over-delivers, which is the right way round for
    `actions.py`'s hide check -- the alternative is sheltering a creature
    from a sword because a gate it could not evaluate defaulted open.
    """
    theirs = squares(world, target)
    mine = squares(world, attacker)
    if not theirs or not mine:
        return Cover.NONE

    # A zone of darkness or fog. The flag was stored and nothing ever read
    # it, so such a zone blocked nothing -- the whole point of the zone.
    # Counted for every attack, not just ranged ones: it is terrain, not a
    # creature, and terrain has always blocked both.
    bodies: set[Square] = set(_blinding_squares(world, attacker, target))
    if ranged:
        side = team(world, target)
        bodies |= {
            sq
            for other in creatures(world)
            if other not in (attacker, target)
            and alive(world, other)
            and team(world, other) is side
            for sq in squares(world, other)
        }

    best = Cover.SUPERIOR
    for src in mine:
        for dst in theirs:
            best = min(best, world.grid.cover(src, dst, blockers=bodies))
    return max(best, _carried_cover(world, target, ctx))


def cover_granters(world: World, attacker: int, target: int) -> list[int]:
    """Which of `target`'s allies are the ones sheltering it from `attacker`.

    `cover_between` answers *how much* cover there is and never *who* is
    giving it, and one item prints the second question: "each enemy granting
    your target cover takes damage". So this asks it the only way it can be
    asked -- take each ally out of the blockers and see whether the cover
    falls. A body nobody is standing behind changes nothing and does not come
    back.

    **Asked per candidate, with that candidate as the only blocker** -- and
    the first version of this asked the opposite question and was wrong.

    It tested whether *removing* each ally reduced the cover, argued at
    length that this was "the printed reading", and was empty exactly when
    the right answer is largest: two allies each individually sufficient
    means removing either leaves the other blocking, so nobody's removal
    matters and nobody is charged. Measured, with the target plainly in
    cover both times:

        a and b stacked, one behind the other:  cover PARTIAL, granters []
        a and b side by side, off the line:     cover PARTIAL, granters []

    So `i778x1` paid out nothing whenever the cover had any redundancy,
    which is most of a real board. Its driver rule passed because the rule's
    own setup put exactly one blocker in the line -- the single arrangement
    where the two readings agree, and therefore no evidence for either.
    #651.

    **And this question already had an answer in the tree.** A content
    helper asked it the sole-blocker way with three callers -- a warlord
    style feat, a ranger one, and a thunder weapon -- before this function
    existed. Adding a fourth implementation rather than finding the first
    three is the fault; `Grid.cover` is the call all of them make, so now
    there is one reader and they cannot disagree.

    Whether a row charges **one** of them or **each** is the row's to
    decide, not this function's: one card prints "one enemy providing cover"
    and another prints "each enemy granting cover". The set comes back whole
    and the row indexes it or loops.

    Ranged only, because that is the only kind of attack a creature can be
    cover against: `cover_between`'s `bodies` set is empty for a melee swing,
    so this is empty too and the caller gets a `[]` rather than a wrong name.
    Terrain is never a granter -- it has no entity to charge -- and neither is
    a carried modifier, for the same reason. #644.
    """
    theirs = squares(world, target)
    mine = squares(world, attacker)
    if not theirs or not mine:
        return []

    side = team(world, target)
    allies_ = [
        other
        for other in creatures(world)
        if other not in (attacker, target)
        and alive(world, other)
        and team(world, other) is side
        and squares(world, other)
    ]
    if not allies_:
        return []

    def traced(body: set[Square]) -> Cover:
        best = Cover.SUPERIOR
        for src in mine:
            for dst in theirs:
                best = min(best, world.grid.cover(src, dst, blockers=body))
        return best

    # **Terrain has to be subtracted, and it was not.** `Grid.cover` unions
    # `self.blocking` into its obstacles on every call, so passing one
    # creature's body still counts every wall on the board -- which made a
    # single pillar between shooter and target turn **every** ally into a
    # granter. The pre-existing content helper this reader replaced had the
    # same flaw and three rows called it, so a feat punishing "the enemy
    # giving your target cover" charged a bystander whenever the cover was
    # really a wall.
    #
    # Found by the redundancy control added for #651, which is the second
    # thing that control caught and was not what it was written for.
    bare = traced(set())
    return [
        other
        for other in allies_
        if traced(set(squares(world, other))) > bare
    ]


def _carried_cover(world: World, target: int, ctx: dict | None = None) -> Cover:
    """Cover a creature carries rather than one it stands behind.

    Everything here traces two positions, so "you and your allies have cover
    while within the zone" had nowhere to go: the zone is not an obstacle
    between anybody, and `blocks_sight` is terrain that blinds both sides.
    Read into this answer rather than added as a third term in
    `resolve.attack`, so that it takes the larger with concealment the way
    traced cover does instead of stacking with it.
    """
    mods = world.get(target, Mods)
    if mods is None or not mods.items:
        return Cover.NONE
    n = mods.total("cover", ctx or {})
    if n >= int(Cover.SUPERIOR):
        return Cover.SUPERIOR
    return Cover.PARTIAL if n > 0 else Cover.NONE


def _blinding_squares(world: World, attacker: int, target: int) -> set[Square]:
    """Squares of sight-blocking zones, minus the ones either party stands in.

    A creature inside the fog is not sheltered from the rest of it, and the
    one standing in it cannot use it as cover against the world outside.
    """
    zones = getattr(world, "zones", None)
    if zones is None:
        return set()
    here = squares(world, attacker) | squares(world, target)
    out: set[Square] = set()
    for _eid, zone in zones.all():
        # **`exempt` is about the looker, not the target.** "Blocks line of
        # sight for every creature except this one" means the exempt
        # creature sees through its own cloud; it does not mean everybody
        # else can see *it*. So the attacker is the one asked, and a zone
        # exempting only the target still blinds the attacker. #Zone.exempt.
        if zone.blocks_sight and attacker not in zone.exempt:
            out |= set(zone.squares) - here
    return out


#: The AC and Reflex bonus each shield grants, by `Gear.shield` index, read
#: from the `armour` table on first ask. Not a literal `{1: 1, 2: 2}`: the
#: numbers are printed and this component does not derive a printed number,
#: which is the rule `etl/CLAUDE.md` states and `trap.perception_dc` is the
#: worked example of. That they happen to equal the index is a coincidence
#: worth not relying on.
_SHIELD_AC: dict[int, int] | None = None


def shield_bonus(world: World, eid: int) -> int:
    """What this creature's shield adds to AC and Reflex. 0 for none.

    Nine rows wanted this number and none could ask for it: a shield's
    contribution is folded into the AC the sheet was built with, and
    `Gear.shield` was a bare `bool` -- so "your shield bonus also applies
    to Fortitude", "raises the light shield's bonus by one" and "trade the
    shield's bonus to AC and Reflex for damage" had nothing to read. The
    kind was known on the class line all along and chargen flattened it on
    the way into `Gear`; see `Gear.shield`.

    `world` is taken and unused by design, so a caller does not have to
    know that: it keeps the signature the other `query` readers have and
    leaves room for a shield granted by something other than gear.
    """
    global _SHIELD_AC
    from .components import Gear

    gear = world.get(eid, Gear)
    held = int(getattr(gear, "shield", 0) or 0) if gear is not None else 0
    if held <= 0:
        return 0
    if _SHIELD_AC is None:
        from combat_engine.db import game

        rows = game().execute(
            "SELECT type, ac_bonus FROM armour WHERE type LIKE '%shield%'"
        ).fetchall()
        found: dict[int, int] = {}
        for row in rows:
            # `light shields` is index 1 and `heavy shields` index 2, which
            # is the order the class line records and `chargen` prints.
            where = 1 if str(row["type"]).startswith("light") else 2
            found.setdefault(where, int(row["ac_bonus"] or 0))
        _SHIELD_AC = found
    return _SHIELD_AC.get(held, 0)


def sealed(world: World, eid: int) -> bool:
    """Is this creature inside something, out of reach in both directions?

    A property of the creature rather than of its square: the square it
    stepped into is solid and already stops everybody else's line. Only
    `c.merge` sets it.
    """
    mods = world.get(eid, Mods)
    return mods is not None and bool(mods.items) and mods.total("sealed") > 0


def line_of_effect(world: World, a: int, b: int) -> bool:
    if sealed(world, a) or sealed(world, b):
        return False
    return any(
        world.grid.line_of_effect(src, dst)
        for src in squares(world, a)
        for dst in squares(world, b)
    )


def lingers(world: World, ref: str, *, by: int | None = None) -> bool:
    """Is anything this power laid still in play?

    The question a card asks as **"recharges when no creature is affected by
    this power"** -- and the reason `Power.recharge_while` exists rather than
    a `Trigger`. There is no moment to watch: the last effect goes away when
    its owner saves, or dies, or it expires, or it is suspended, or the
    creature holding it drops. Subscribing to all five and re-asking is both
    the hard way and the fragile way, because missing one route leaves the
    power gone for the rest of the fight and says nothing.

    Matched on the effect's `label`, which is how an effect is tied back to
    the row that laid it -- `Effect.source` is the *entity* that cast it, not
    the card. Every verb these rows use already labels with the ref and has
    done since before this was written: `c.condition` passes `self.ref`,
    `c.dominate` passes `f"{self.ref} dominate"`, `c.form` passes
    `label or self.ref`. So this reads a convention rather than needing one
    imposed.

    A zone counts, which is what "when all of this power's <zones> have
    ended" needs: a zone's effect is owned by the zone entity, so nothing the
    caster owns mentions it -- the same blind spot `Effects.sustaining`
    records -- but the label still names the row.

    **`by=` narrows to one creature's own handiwork, and matters whenever two
    of a kind are on the board.** Two of these monsters appear as a pair in
    their own stat block, so without it either one's hold keeps both their
    powers spent.
    """
    return any(
        (eff.label == ref or eff.label.startswith(f"{ref} "))
        and (by is None or eff.source == by)
        for eff in world.effects.live.values()
    )

def granted_amount(
    world: World,
    eid: int,
    ref: str,
    default: int,
    ctx: dict[str, Any] | None = None,
) -> int:
    """How big a number a named mechanic hands out, for this creature.

    **`Cast.amount_for`'s body, moved down here so it has one reader.**
    `resolve._mark_penalty` needs the same question and has no `Cast` -- it
    holds a `world` and the creatures -- and the obvious shape was to repeat
    the four lines there. That is a second reader of one store, which drifts:
    `Weapon.hands` answered differently by provenance for exactly that reason
    (#562), and a whole session went into reconciling it. `query.py` is below
    both and already has 325 importers.

    **The largest wins**, where `dice_for` takes the first that matches. Two
    rows raising one grant are not additive and the better applies -- and
    taking the first would make the answer depend on the order the effects
    were laid, which is not a rule anybody printed.

    **The default is a fallback, not a floor.** `drivers.aid_grants` caught
    that written as `max(default, ...)`: `f2444` sets its granted bonus to 0
    because its reroll *replaces* the +2, and a floor quietly kept the 2.
    """
    known = world.get(eid, Powers)
    if known is None:
        return default
    seen = ctx or {}
    laid = [a for a, gate in known.amounts.get(ref, ())
            if gate is None or gate(seen)]
    return max(laid) if laid else default


def leash_of(world: World, eid: int) -> tuple[tuple[int, int], int] | None:
    """Where this creature is tethered and how far it may stray, or None.

    Resolves a creature anchor to that creature's **current** square, which
    is the half that makes "no more than 2 squares from a held creature"
    work while the holder moves. A dead or departed anchor returns None --
    the leash is cut rather than measured against a corpse's last position.
    #512.
    """
    from .components import Leash, Position

    tie = world.get(eid, Leash)
    if tie is None or tie.radius <= 0:
        return None
    if tie.to is not None:
        if not alive(world, tie.to):
            return None
        at = world.get(tie.to, Position)
        return (at.square, tie.radius) if at is not None else None
    return (tie.square, tie.radius) if tie.square is not None else None


def kept_away_from(world: World, eid: int) -> tuple[int, int] | None:
    """The square this creature may not get closer to, and how close it is.

    `(anchor_square, distance_now)`, so the caller's test is
    `grid_distance(sq, anchor) >= distance_now` -- which is *"cannot move
    closer"* exactly. The distance is measured **now** rather than stored
    when the effect landed, for the reason `Leash.away_from` gives: the
    clause forbids reducing the gap, and a frozen number would pin a
    creature the anchor had since walked towards.

    `None` when there is no such hold, when the anchor is dead or gone, or
    when this creature has no position to measure from -- the same three
    waivers `leash_of` makes, and a dead anchor cuts the restriction rather
    than measuring against a corpse. #728.
    """
    from .components import Leash, Position
    from .grid import distance as grid_distance

    tie = world.get(eid, Leash)
    if tie is None or tie.away_from is None:
        return None
    if not alive(world, tie.away_from):
        return None
    anchor = world.get(tie.away_from, Position)
    mine = world.get(eid, Position)
    if anchor is None or mine is None:
        return None
    return (anchor.square, grid_distance(mine.square, anchor.square))


def since_turn_ended(world: World, eid: int) -> int:
    """The `seq` after which something counts as "since the end of your last
    turn".

    **The bus log already answers this and two rows said nothing did.**
    `i2303p1`'s note read "nothing asks the world who has attacked whom
    since when" and `i2803p1`'s "nothing keeps that history: the events are
    gone by the time this row is asked" -- and neither is true. `Bus.log`
    keeps every event of the fight with a monotonic `seq`, and `TurnEnd`
    carries the actor, so the boundary is one `max()` and the history is a
    slice. No component, no writer, nothing to keep in step.

    `-1` when this creature has not ended a turn yet, which makes the whole
    fight so far count -- the right answer for a row used in round one,
    where "since the end of your last turn" is "since the fight began".
    """
    return max(
        (
            e.seq
            for e in world.bus.log
            if e.kind == "TurnEnd" and getattr(e, "actor", None) == eid
        ),
        default=-1,
    )


def attacked_since(
    world: World, victim: int, by: int, *, since: int | None = None
) -> bool:
    """Has that creature attacked this one since the boundary?

    `AttackDeclared` rather than `Hit`: the printed line is "a target that
    has **attacked** you", which a miss satisfies. Declared rather than
    rolled because a cancelled attack was still an attack made.
    """
    mark = since_turn_ended(world, victim) if since is None else since
    return any(
        e.seq > mark
        and e.kind == "AttackDeclared"
        and getattr(e, "attacker", None) == by
        and getattr(e, "target", None) == victim
        for e in world.bus.log
    )


def damaged_since(
    world: World,
    victim: int,
    by: int,
    *,
    since: int | None = None,
    or_an_ally: bool = False,
) -> bool:
    """Has that creature dealt damage to this one since the boundary?

    `or_an_ally` is the printed "dealt damage to you **or an ally**", which
    one of the two rows prints and the other does not. The ally list is
    read at the moment of the question rather than remembered, which is the
    same simplification `query.allies` makes everywhere else: a creature
    that has since changed sides is read as it stands now.
    """
    mark = since_turn_ended(world, victim) if since is None else since
    who = {victim}
    if or_an_ally:
        who |= set(allies(world, victim))
    return any(
        e.seq > mark
        and e.kind == "DamageApplied"
        and getattr(e, "source", None) == by
        and getattr(e, "target", None) in who
        and getattr(e, "amount", 0) > 0
        for e in world.bus.log
    )


def dropped_since(
    world: World,
    victim: int,
    by: int,
    *,
    since: int | None = None,
    or_an_ally: bool = False,
) -> bool:
    """Has that creature put this one on the floor since the boundary?

    `Dropped` and not a hit-point read: the event is announced for dying
    and for dead outright, which is what "reduced to 0 hit points or fewer"
    means, and a creature healed back up since would read False off its
    sheet while the printed clause still counts it.
    """
    mark = since_turn_ended(world, victim) if since is None else since
    who = {victim}
    if or_an_ally:
        who |= set(allies(world, victim))
    return any(
        e.seq > mark
        and e.kind == "Dropped"
        and getattr(e, "source", None) == by
        and getattr(e, "actor", None) in who
        for e in world.bus.log
    )


def difficulty(level: int, band: str) -> int | None:
    """The printed DC for a named difficulty at a level. `None` if unknown.

    4e prints many checks as a **band** rather than a number -- "Athletics
    check (hard DC)" -- against one table of Easy/Moderate/Hard DCs by
    level. `terrain.check_band` holds that word on 15 rows and
    `disease.dc_shape = 'band'` on 8, each with the DC left null for want of
    this. #491.

    The table lives in `engine/difficulty.py`, read off the compendium's
    `Glossary` entry 384 rather than recalled -- it has been got wrong here
    from memory before. This is the reader, and it is here because this is
    where readers live and where `docs/symbols/reading.md` finds them.

    `None` means *unknown*, never "no DC": an unrecognised band is a parse
    fault upstream, and a null level cannot be resolved at all, which is the
    case the 8 band-shaped diseases are in -- their `level` is null too.
    """
    from .difficulty import difficulty as _dc

    return _dc(level, band)
