"""Facts derived from the board, asked rather than stored.

Combat advantage is the reason this module exists. A dozen unrelated things
grant it -- flanking, prone, blinded, stunned, a power that says so -- and
storing a flag means every one of them has to remember to take it back. So
nothing stores it; it is recomputed from the board whenever an attack asks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .components import (
    Barrier,
    Companion,
    Conditions,
    Defenses,
    Health,
    Mods,
    Movement,
    Position,
    Side,
    Stats,
)
from .conditions import rules
from .grid import Square, between, spread
from .types import Condition, Cover, Defense, Relation, Team

if TYPE_CHECKING:
    from .ecs import World


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
        if world.get(e, Companion) is None and world.get(e, Barrier) is None
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
        return [
            w for w in out
            if what in w.properties or w.group == what or w.category == what
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


def conscious(world: World, eid: int) -> bool:
    return alive(world, eid) and not is_(world, eid, Condition.UNCONSCIOUS)


def is_(world: World, eid: int, c: Condition) -> bool:
    conds = world.get(eid, Conditions)
    return conds is not None and conds.has(c)


def active(world: World, eid: int) -> list[Condition]:
    conds = world.get(eid, Conditions)
    return conds.active if conds else []


def distance_between(world: World, a: int, b: int) -> int:
    return between(squares(world, a), squares(world, b))


def adjacent(world: World, a: int, b: int) -> bool:
    return bool(spread(squares(world, a), 1) & squares(world, b))


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
        cap = rules(c).speed_cap
        if cap is not None:
            base = min(base, cap)
        halved = halved or rules(c).halve_speed
        if rules(c).cannot_move:
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
    """
    defs = world.need(eid, Defenses)
    base = defs.base(d) + level_term(world, eid, defs.scale)
    mods = world.get(eid, Mods)
    if mods is not None:
        base += mods.total(d.value, ctx or {})
    for c in active(world, eid):
        base += rules(c).defences.get(d, 0)
    return base


def attack_penalty(world: World, eid: int) -> int:
    """What the attacker's own conditions cost it, before modifiers."""
    return sum(rules(c).attack for c in active(world, eid))


def deals_half(world: World, eid: int) -> bool:
    return any(rules(c).weakened for c in active(world, eid))


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
    from .dsl import get

    known = world.get(eid, Powers)
    if known is None:
        return "none"
    near = far = False
    for ref in known.all:
        p = get(ref)
        if p is None or not p.is_attack:
            continue
        for branch in p.branches:
            kind = p.reach_of(branch).kind
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
    from .components import Ident

    profile = range_profile(world, eid)
    if profile in ("melee", "none"):
        return False
    if profile == "ranged":
        return True
    ident = world.get(eid, Ident)
    if ident is None or not ident.ref.startswith("m"):
        return False
    from combat_engine.content.loader import load

    try:
        return (load(ident.ref).row.get("role") or "") in _STANDOFF
    except Exception:
        return False


def is_trap(world: World, eid: int) -> bool:
    from .components import Trap

    return world.get(eid, Trap) is not None


def is_conjuration(world: World, eid: int) -> bool:
    from .components import Conjuration

    return world.get(eid, Conjuration) is not None


def can_act(world: World, eid: int) -> bool:
    # A trap and a conjuration have no hit points to be unconscious about.
    # Without this they failed `conscious` and could never make the attack
    # they exist to make.
    if is_trap(world, eid) or is_conjuration(world, eid):
        return True
    return conscious(world, eid) and not any(rules(c).cannot_act for c in active(world, eid))


def can_react(world: World, eid: int) -> bool:
    return can_act(world, eid) and not any(rules(c).no_reactions for c in active(world, eid))


def takes_half(world: World, eid: int) -> bool:
    """Insubstantial: everything that reaches this creature is halved."""
    return any(rules(c).insubstantial for c in active(world, eid))


def can_shift(world: World, eid: int) -> bool:
    """A shift is barred separately from a walk, and by different powers."""
    return can_move(world, eid) and not any(rules(c).no_shift for c in active(world, eid))


def can_move(world: World, eid: int) -> bool:
    return can_act(world, eid) and not any(rules(c).cannot_move for c in active(world, eid))


def can_walk(world: World, eid: int) -> bool:
    """"It cannot use move actions to walk or run", but it may still shift.

    The exact mirror of `c.rooted`, and neither condition says it:
    `immobilized` bars the shift as well, which is a stronger card than the
    rows printing this one. Held as a modifier rather than a condition
    because nothing else about the creature changes -- it is not slowed, it
    grants nothing, it is simply not going anywhere on its feet.
    """
    if not can_move(world, eid):
        return False
    mods = world.get(eid, Mods)
    return not (mods is not None and mods.items and mods.total("no_walk", {}) > 0)


# -- combat advantage -------------------------------------------------------


def grants_ca(world: World, eid: int) -> bool:
    """True when the creature grants combat advantage to everyone."""
    return any(rules(c).grants_ca for c in active(world, eid))


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


def has_combat_advantage(world: World, attacker: int, target: int) -> bool:
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
    ca_ctx = {"attacker": attacker, "target": target}
    denied = world.get(target, Mods)
    if denied is not None and denied.items and denied.total("no_advantage", ca_ctx) > 0:
        return False
    if grants_ca(world, target):
        return True
    if world.relations.holds(Relation.GRANTS_CA_TO, target, attacker):
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


def immune_to(world: World, eid: int, cond: Condition) -> bool:
    """Can this condition not be laid on this creature at all?

    Distinct from curing one: "you cannot be marked or slowed until the end
    of your next turn" is a window in which the condition never arrives,
    and stripping it afterwards is a different sentence that leaves every
    rider hung on `ConditionApplied` already paid out.
    """
    mods = world.get(eid, Mods)
    if mods is None or not mods.items:
        return False
    return mods.total(f"immune to {cond.value}", {}) > 0


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


def unseen_by(world: World, watcher: int, who: int) -> bool:
    """Is `who` invisible to `watcher`?

    The relation alone was the whole answer, so "you can see invisible
    creatures" -- printed by two classes and every darkvision-adjacent
    monster trait -- had nothing to switch off. Asked here rather than at
    each of the two places that read `HIDDEN_FROM`, so the sight and the
    combat advantage can never disagree.
    """
    if sight_capped(world, watcher, who):
        return True
    return world.relations.holds(Relation.HIDDEN_FROM, who, watcher) and not sees_through(
        world, watcher, who
    )


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
    """
    ctx = ctx or {}
    mine = world.get(attacker, Mods)
    theirs = world.get(target, Mods)
    return max(
        mine.total("ignore_cover", ctx) if mine is not None and mine.items else 0,
        theirs.total("no_cover", ctx) if theirs is not None and theirs.items else 0,
    )


def cover_between(
    world: World, attacker: int, target: int, *, ranged: bool = False
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
    return max(best, _carried_cover(world, target))


def _carried_cover(world: World, target: int) -> Cover:
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
    n = mods.total("cover", {})
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
        if zone.blocks_sight:
            out |= set(zone.squares) - here
    return out


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
