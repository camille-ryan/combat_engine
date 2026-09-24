"""Turning the engine's state into what the page reads.

One direction only. Nothing here decides anything or touches the world; it
reads and formats. The action list in particular comes straight from
`actions.legal` -- the page and any policy are shown the same options in the
same order, so a click cannot do something a policy could not have chosen.
"""

from __future__ import annotations

from combat_engine.engine import (
    Action,
    Budget,
    Conditions,
    Defences,
    Defenses,
    Gear,
    Health,
    Ident,
    Initiative,
    Position,
    Powers,
    Side,
    Stats,
    Team,
    get,
    usable,
)
from combat_engine.engine.actions import legal
from combat_engine.engine.dsl import aim_points, area_of, candidates
from combat_engine.engine.durations import When
from combat_engine.engine.events import Event
from combat_engine.engine.movement import OVERHEAD, mode_of, reachable, risk_along
from combat_engine.engine.query import (
    alive,
    creatures,
    defence,
    is_,
    speed,
    squares,
)
from combat_engine.engine.types import ActionType, Condition, Defense
from combat_engine.engine.zones import Zone

from . import dto
from .session import Session
from .wire import Wire

RANK = {"minion": "minion", "elite": "elite", "solo": "solo"}


def state(session: Session, seq: int = 0) -> dto.EncounterStateDTO:
    session.wire.refresh(session.world)
    world, wire = session.world, session.wire
    actor = session.current
    options = session.options()

    return dto.EncounterStateDTO(
        id=session.id,
        round=world.round,
        seed=session.seed,
        status=session.status,
        current=wire.id(actor),
        awaiting_input=session.awaiting,
        winner=session.encounter.winner.value if session.encounter.winner else None,
        rounds=world.round if session.encounter.finished else None,
        board=board(session),
        actors=[actor_dto(session, eid) for eid in initiative(session)],
        options=[option_dto(session, i, o) for i, o in enumerate(options)],
        roster=roster(session, options),
        economy=economy(session),
        movement=movement(session),
        pending=pending(session),
        seq=len(world.bus.log),
        scaling=world.scaling.describe(),
    )


def initiative(session: Session) -> list[int]:
    """Everyone, in the order they take their turns.

    `creatures` is the order the world spawned them in, which is nobody's
    turn order -- and it is what the page's initiative strip was drawing,
    because the strip is `actors` and nothing else ever sorted it.
    `Encounter.order` is the roll, and the dead keep their slot in it.

    Anything not in that list -- something summoned mid-fight, or a snapshot
    taken before the fight started -- follows in spawn order rather than
    being dropped.
    """
    order = {eid: i for i, eid in enumerate(session.encounter.order)}
    late = len(order)
    return sorted(creatures(session.world), key=lambda eid: order.get(eid, late))


# --------------------------------------------------------------------------
# The board
# --------------------------------------------------------------------------


def board(session: Session) -> dto.BoardDTO:
    world, wire = session.world, session.wire
    return dto.BoardDTO(
        width=world.grid.width,
        height=world.grid.height,
        blocking=sorted(world.grid.blocking),
        difficult=sorted(world.difficult()),
        obscuring=[],
        zones=[
            dto.ZoneDTO(
                id=wire.zone(eid),
                owner=wire.id(zone.owner),
                squares=sorted(zone.squares),
                label=wire.power(zone.label),
            )
            for eid, zone in world.each(Zone)
        ],
    )


def actor_dto(session: Session, eid: int) -> dto.ActorDTO:
    world, wire = session.world, session.wire
    health = world.need(eid, Health)
    pos = world.need(eid, Position)
    stats = world.get(eid, Stats)
    side = world.get(eid, Side)
    conds = world.get(eid, Conditions)
    res = world.get(eid, Defences)
    ident = world.need(eid, Ident)

    return dto.ActorDTO(
        id=wire.id(eid) or str(eid),
        label=wire.label(eid),
        side="pc" if side and side.team is Team.PC else "npc",
        square=pos.square,
        squares=sorted(pos.squares),
        hp=health.hp,
        hp_max=health.max_hp,
        temp_hp=health.temp,
        surges=health.surges,
        surges_max=health.surges,
        bloodied=health.bloodied,
        bloodied_value=health.max_hp // 2,
        dead=not alive(world, eid),
        ac=defence(world, eid, Defense.AC),
        fort=defence(world, eid, Defense.FORT),
        ref=defence(world, eid, Defense.REF),
        will=defence(world, eid, Defense.WILL),
        conditions=[c.value for c in (conds.active if conds else [])],
        effects=[
            condition_dto(session, e)
            for e in [*world.effects.of(eid), *world.effects.sustaining(eid)]
        ],
        traits=[],
        is_current=eid == session.current,
        level=stats.level if stats else 1,
        role=_monster_field(ident.ref, "role"),
        rank=_rank(ident.ref),
        size=pos.size.value,
        speed=speed(world, eid),
        initiative_mod=(init.bonus if (init := world.get(eid, Initiative)) else 0),
        senses=_monster_field(ident.ref, "senses"),
        mtype=_monster_field(ident.ref, "kind"),
        origin=_monster_field(ident.ref, "origin"),
        resist=_damage_line(res.resist if res else {}),
        vulnerable=_damage_line(res.vulnerable if res else {}),
        immune=", ".join(sorted(d.value for d in res.immune)) if res and res.immune else None,
        threat=_threat(session, eid),
        subtypes=None,
    )


def condition_dto(session: Session, effect) -> dto.ConditionDTO:  # noqa: ANN001
    wire = session.wire
    bits = [c.value for c in effect.conditions]
    if effect.ongoing:
        bits.append(f"ongoing {effect.ongoing[0]} {effect.ongoing[1].value}")
    for _eid, mod in effect.mods:
        bits.append(f"{mod.value:+d} {mod.what}")
    for kind, source, _target in effect.relations:
        bits.append(f"{kind.value.replace('_', ' ')} {wire.label(source)}")
    if effect.sustain_cost is not None:
        # Said plainly, because the rule here is not the printed one: this
        # keeps itself going unless the action it names goes elsewhere.
        bits.append(f"holds unless you spend your {effect.sustain_cost.value}")
    return dto.ConditionDTO(
        name=wire.power(effect.label) if effect.label else "effect",
        text=", ".join(bits) or "-",
        duration=_duration_text(session, effect),
        source=wire.id(effect.source),
        ongoing=effect.ongoing[0] if effect.ongoing else 0,
        ongoing_type=effect.ongoing[1].value if effect.ongoing else None,
        save_ends=effect.when is When.SAVE_ENDS,
    )


def _duration_text(session: Session, effect) -> str:  # noqa: ANN001
    """Say whose clock it is on, not just what kind of clock it is."""
    who = session.wire.label(effect.clock)
    return {
        When.EONT: f"end of {who}'s next turn",
        When.SONT: f"start of {who}'s next turn",
        When.EOTNT: f"end of {who}'s next turn",
        When.SOTNT: f"start of {who}'s next turn",
        When.SAVE_ENDS: "save ends",
        When.ENCOUNTER: "end of the fight",
        When.STANCE: "stance",
        When.SUSTAIN: "while sustained",
        When.INSTANT: "instant",
    }[effect.when]


def _damage_line(values: dict) -> str | None:
    return ", ".join(f"{n} {d.value}" for d, n in sorted(values.items())) or None


def _monster_field(ref: str, column: str) -> str | None:
    if not ref.startswith("m"):
        return None
    from combat_engine.content.loader import load

    try:
        return load(ref).row.get(column) or None
    except KeyError:
        return None


def _rank(ref: str) -> str:
    if not ref.startswith("m"):
        return "standard"
    from combat_engine.content.loader import load

    try:
        row = load(ref).row
    except KeyError:
        return "standard"
    for flag, name in RANK.items():
        if row.get(flag):
            return name
    return "standard"


def _threat(session: Session, eid: int) -> float:
    """How dangerous this creature is, as a share of one character's health.

    Deliberately the scorer's kind of number rather than raw damage: a flat
    figure quietly changes meaning as the party levels, and two creatures on
    one board are being compared here.
    """
    world = session.world
    known = world.get(eid, Powers)
    if known is None:
        return 0.0
    best = 0.0
    foes = [f for f in creatures(world) if alive(world, f)]
    for ref in known.all:
        p = get(ref)
        if p is None or p.attack is None:
            continue
        for foe in foes:
            mine, theirs = world.get(eid, Side), world.get(foe, Side)
            if mine and theirs and mine.team is theirs.team:
                continue
            best = max(best, p.hit_chance(world, eid, foe))
    return round(best, 3)


# --------------------------------------------------------------------------
# Options and the roster
# --------------------------------------------------------------------------


def option_dto(session: Session, index: int, action: Action) -> dto.OptionDTO:
    world, wire = session.world, session.wire
    actor = session.current
    p = get(action.ref) if action.ref else None

    affected: list = []
    if p is not None and p.reach.kind in ("close_burst", "close_blast", "area_burst"):
        affected = sorted(area_of(world, actor, p, action.origin))

    return dto.OptionDTO(
        index=index,
        kind=action.kind,
        label=_option_label(session, action, p),
        cost=action.cost.value,
        targets=[wire.id(t) or str(t) for t in action.targets],
        origin=action.origin,
        affected=affected,
        path=list(action.path),
        forecast=_forecast(session, action, p),
        notes=_notes(session, action, p),
        pays=_pays(session, action).value,
        affordable=session.encounter.can_spend(actor, action.cost) if actor else False,
        cost_note=_cost_note(session, action),
        score=round(session.policy.score(world, session.encounter, actor, action), 2)
        if actor
        else 0.0,
    )


def _notes(session: Session, action: Action, p) -> list[str]:  # noqa: ANN001
    """What the option costs beyond its action, in words.

    Right now that is one thing: a ranged or area power used with somebody
    adjacent hands them a free attack, and a player who cannot see that
    coming will take it every time.
    """
    from combat_engine.engine.query import adjacent, alive

    if p is None or not p.provokes:
        return []
    actor = session.current
    close = [
        e
        for e in session.world.entities
        if e != actor
        and alive(session.world, e)
        and adjacent(session.world, actor, e)
        and session.world.get(e, Side)
        and session.world.get(e, Side).team is not Team.PC
    ]
    if not close:
        return []
    who = ", ".join(session.wire.label(e) for e in close)
    return [f"provokes an opportunity attack from {who}"]


def _option_label(session: Session, action: Action, p) -> str:  # noqa: ANN001
    """What this option says on its button.

    An area power gets one option per square it may be centred on, and they
    are genuinely different choices -- so the label has to say which. Without
    the origin, a burst with thirty placements is thirty buttons reading the
    same words, and a player cannot tell them apart or see that the list is
    ordered by what each one catches.
    """
    wire = session.wire
    if action.kind == "power":
        name = wire.power(action.ref)
        who = ", ".join(wire.label(t) for t in action.targets)
        if action.origin is not None:
            spot = f"at {tuple(action.origin)}"
            return f"{name} {spot} -> {who}" if who else f"{name} {spot}"
        return f"{name} -> {who}" if who else name
    if action.kind == "move":
        return f"move to {tuple(action.dest)}"
    if action.kind == "shift":
        return f"shift to {tuple(action.dest)}"
    return {"stand": "stand up", "second_wind": "second wind", "end": "end turn"}.get(
        action.kind, action.kind
    )


def _pays(session: Session, action: Action) -> ActionType:
    """Which action slot this really costs.

    A move made with the move action already gone is paid out of the standard
    action. The page offered it as free and the server charged the attack,
    until that was said on the wire.
    """
    from combat_engine.engine.types import DOWNGRADES

    actor = session.current
    budget = session.world.get(actor, Budget) if actor else None
    if budget is None or action.cost not in DOWNGRADES:
        return action.cost
    for slot in DOWNGRADES[action.cost]:
        if getattr(budget, slot.value) > 0:
            return slot
    return action.cost


def _cost_note(session: Session, action: Action) -> str | None:
    paid = _pays(session, action)
    if paid is action.cost:
        return None
    return f"spends your {paid.value} action"


def _forecast(session: Session, action: Action, p) -> dto.ForecastDTO | None:  # noqa: ANN001
    if p is None or p.attack is None or not action.targets:
        return None
    world = session.world
    actor = session.current
    chances = [p.hit_chance(world, actor, t) for t in action.targets]
    mean = sum(chances) / len(chances)
    # Damage is not knowable without running the power -- a body is code --
    # so this is what the policy has learned from watching, defaulting to a
    # neutral figure rather than a confident wrong one.
    per_hit = session.policy.memory.worth(action.ref, 6.0) if session.policy.memory else 6.0
    expected = sum(chances) * per_hit
    kills = sum(
        1
        for t, c in zip(action.targets, chances, strict=False)
        if c > 0.5 and (h := world.get(t, Health)) and h.hp <= per_hit
    )
    return dto.ForecastDTO(
        hit_chance=round(mean, 3),
        expected_damage=round(expected, 1),
        kills_likely=kills,
        summary=f"{mean:.0%} to hit, about {expected:.0f} damage",
    )


def roster(session: Session, options: list[Action]) -> list[dto.PowerDTO]:
    """The acting creature's whole kit, usable or not.

    Everything it carries, with a reason on the ones it cannot use, because
    "the attack you would get by closing two squares" is exactly what a
    player needs to see and the legal-action list cannot show it.
    """
    world = session.world
    actor = session.current
    if actor is None:
        return []
    known = world.get(actor, Powers)
    if known is None:
        return []

    by_ref: dict[str, list[int]] = {}
    for i, action in enumerate(options):
        if action.ref:
            by_ref.setdefault(action.ref, []).append(i)

    # The same order `session.roster_refs` produces, because the page sends
    # back a position in this list and both ends have to agree on it.
    out: list[dto.PowerDTO] = []
    for ref in session.roster_refs():
        p = get(ref)
        if p is None:
            continue
        ok, why = usable(world, actor, p)
        # Both halves of a two-branch row, unioned. The squares are what the
        # board offers, and a click resolves to the first option that reaches
        # it -- so an adjacent enemy is taken in melee and a distant one at
        # range, which is what a player means by clicking either.
        aims_at = sorted(
            {sq for b in p.branches for sq in _clickable(world, actor, p, b)}
        )
        indices = by_ref.get(ref, [])
        printed = session.wire.printed(ref)
        affordable = session.encounter.can_spend(actor, p.action)
        if not affordable and ok:
            ok, why = False, "no action left"
        out.append(
            dto.PowerDTO(
                name=session.wire.power(ref),
                action=p.action.value,
                cost=p.action.value,
                usage=p.usage.value + (f" {p.recharge}+" if p.recharge else ""),
                range_text=str(p.reach),
                keywords=[k.value for k in p.keywords],
                attack_text=printed.get("attack") or (str(p.attack) if p.attack else None),
                damage=printed.get("damage") or None,
                requirement_text=printed.get("requirement") or p.requires_text or None,
                hit_text=printed.get("hit") or None,
                miss_text=printed.get("miss") or None,
                effect_text=printed.get("effect") or None,
                targets=str(p.target),
                available=bool(indices),
                reason=None if indices else (why or "cannot be used here"),
                squares=aims_at,
                footprints=_footprints(world, actor, p, aims_at),
                aimed=[],
                option_index=indices[0] if indices else None,
                option_indices=indices,
                option_label=" or ".join(
                    p.label_of(b) for b in p.branches
                ) if len(p.branches) > 1 else None,
                affordable=affordable,
                pays=_pays(session, options[indices[0]]).value if indices else None,
                cost_note=_cost_note(session, options[indices[0]]) if indices else None,
            )
        )
    return out


def _clickable(world, actor: int, p, branch: int = 0) -> list:  # noqa: ANN001
    """The squares a player may click to use this power.

    Two different questions wear the same name. For a melee or ranged power
    it is *where a target may be standing* -- the reach. For a burst or a
    blast it is *where the power may be centred*, which for an area burst 1
    within 10 is everywhere within ten and for a blast 3 is the ring two out.

    Handing back the covered area for an area power is why one could not be
    aimed: the page highlighted the squares the burst would fill if cast on
    the caster's own head, and a click anywhere else did nothing.
    """
    if not p.is_attack:
        return []
    if p.reach_of(branch).kind in ("area_burst", "close_blast"):
        return aim_points(world, actor, p)
    return sorted(area_of(world, actor, p, None, branch))


def _footprints(world, actor: int, p, aims_at: list) -> dict[str, list]:  # noqa: ANN001
    """What each aim square would actually catch.

    Only for the two shapes where the square you click is not the square you
    hit. A player placing a blast 3 could see the ring it may be pointed at
    and nothing about what it would cover, so the choice was made blind and
    read afterwards off the log. The shape is a rule, which is why it is
    worked out here and not in the browser.
    """
    if p.reach.kind not in ("area_burst", "close_blast"):
        return {}
    return {f"{x},{y}": sorted(area_of(world, actor, p, (x, y))) for x, y in aims_at}


def economy(session: Session) -> dto.EconomyDTO:
    actor = session.current
    budget = session.world.get(actor, Budget) if actor else None
    if budget is None:
        return dto.EconomyDTO()
    spent = [
        name
        for name, left in (("standard", budget.standard), ("move", budget.move),
                           ("minor", budget.minor))
        if left <= 0
    ]
    buys = {}
    if budget.standard > 0:
        buys["standard"] = "standard, move or minor"
    if budget.move > 0:
        buys["move"] = "move or minor"
    if budget.minor > 0:
        buys["minor"] = "minor"
    return dto.EconomyDTO(spent=spent, buys=buys)


def movement(session: Session) -> dto.MovementDTO | None:
    """Where the acting creature can walk this turn, and what it costs there.

    Both lists are inside the creature's **speed** -- this is one move
    action, not two -- and they split by **risk**, not by cost. `risky` is
    the squares whose route provokes an opportunity attack or walks through
    an enemy's zone; `free` is the rest. A square two moves' worth of
    difficult ground away is still green if nothing can hit you on the way,
    which is the question a player is actually asking.

    It used to split by cost, while the page's own legend said "move,
    provokes" -- so the colour meant one thing and the key beside it
    promised another.

    An earlier version had the second list mean "reachable by spending the
    standard action as a second move", which doubled the highlighted range
    and told a player they could walk twice as far as they could.

    Every route comes too. The page draws one when the player points at a
    square, and it must be the same route the move would take -- working it
    out a second time in JavaScript is how the drawn path and the walked
    path come to disagree.
    """
    world = session.world
    actor = session.current
    if actor is None or session.encounter.finished:
        return None
    budget = world.get(actor, Budget)
    if budget is None:
        return None
    if not session.encounter.can_spend(actor, ActionType.MOVE):
        return dto.MovementDTO()

    pace = speed(world, actor)
    routes = reachable(world, actor, pace)
    free, risky = [], []
    paths: dict[str, list] = {}
    warnings: dict[str, str] = {}
    for square, path in sorted(routes.items()):
        key = f"{square[0]},{square[1]}"
        paths[key] = list(path)
        why = risk_along(world, actor, list(path))
        if why:
            warnings[key] = why
            risky.append(square)
        else:
            free.append(square)

    mode = mode_of(world, actor, None)
    step = reachable(world, actor, 1, mode="walk" if mode in OVERHEAD else None)
    return dto.MovementDTO(
        free=free, risky=risky, shift=sorted(step), paths=paths, warnings=warnings
    )


def pending(session: Session) -> dto.PendingDTO | None:
    q = session.gate.question
    if q is None:
        return None
    wire = session.wire
    answers = []
    for i, option in enumerate(q.options):
        if isinstance(option, int):
            answers.append(
                dto.PendingAnswerDTO(index=i, label=wire.label(option), actor=wire.id(option))
            )
        elif isinstance(option, tuple) and len(option) == 2:
            answers.append(
                dto.PendingAnswerDTO(index=i, label=f"{option}", squares=[option])
            )
        else:
            answers.append(dto.PendingAnswerDTO(index=i, label=str(option)))
    return dto.PendingDTO(
        kind=q.kind,
        chooser=wire.id(q.chooser) or str(q.chooser),
        prompt=q.prompt,
        answers=answers,
        default=0,
    )


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------


#: Engine event names, in the vocabulary the page speaks.
#:
#: The page was written against the first attempt's event names and came over
#: unchanged, so this is where the two meet. Three of these are load-bearing
#: -- `anim.js` plays exactly `moved`, `attack_rolled` and `attack_hit`, and
#: an event under any other name is logged and not shown. The rest are here so
#: the whole stream reads in one idiom rather than two.
WIRE_KIND = {
    "Moved": "moved",
    "MoveStart": "move_start",
    "MoveEnd": "move_end",
    "AttackDeclared": "attack_declared",
    "AttackRolled": "attack_rolled",
    "Hit": "attack_hit",
    "Miss": "attack_miss",
    "DamageApplied": "damage_taken",
    "DamageRolled": "damage_rolled",
    "Healed": "healed",
    "TempHP": "temp_hp",
    "Bloodied": "bloodied",
    "Dropped": "dropped",
    "Died": "died",
    "ConditionApplied": "condition_applied",
    "ConditionEnded": "condition_ended",
    "RelationSet": "relation_set",
    "RelationCleared": "relation_cleared",
    "SavingThrow": "saving_throw",
    "EffectExpired": "effect_expired",
    "PowerUsed": "power_used",
    "TurnStart": "turn_start",
    "TurnEnd": "turn_end",
    "RoundStart": "round_start",
    "RoundEnd": "round_end",
    "ZoneCreated": "zone_created",
    "ZoneEnded": "zone_ended",
    "ZoneEntered": "zone_entered",
    "ZoneExited": "zone_exited",
    "ForcedMove": "forced_move",
    "OpportunityWindow": "opportunity",
    "EnterSquare": "entered_square",
    "LeaveSquare": "left_square",
    "AdjacencyGained": "adjacent_gained",
    "AdjacencyLost": "adjacent_lost",
    "Note": "note",
}


def event_dto(session: Session, event: Event) -> dto.EventDTO:
    wire = session.wire
    data = event.wire()
    actor = data.get("actor") or data.get("attacker") or data.get("source")
    target = data.get("target")
    payload = {k: _wire_value(wire, k, v) for k, v in data.items()}
    # `Moved` spells its fields `from_` and `to` because `from` is a keyword
    # in Python and is not one in JavaScript.
    if "from_" in payload:
        payload["from"] = payload.pop("from_")
    return dto.EventDTO(
        # One-based on the wire. The page treats `from` as exclusive and only
        # animates events newer than its cursor, which starts at zero -- so a
        # zero-based first event is never shown.
        seq=event.seq + 1,
        kind=WIRE_KIND.get(event.kind, event.kind),
        actor=wire.id(actor) if isinstance(actor, int) else None,
        target=wire.id(target) if isinstance(target, int) else None,
        text=narrate(session, event),
        data=payload,
    )


def _wire_value(wire: Wire, key: str, value):  # noqa: ANN001, ANN202
    """Translate the payload keys that hold a creature id."""
    holders = ("actor", "attacker", "source", "target", "other", "provoker", "owner")
    if key in holders and isinstance(value, int):
        return wire.id(value) or value
    if key == "targets" and isinstance(value, list):
        return [wire.id(v) or v for v in value]
    if key == "power" and isinstance(value, str):
        return wire.power(value)
    return value


#: Events that begin a new sentence. Everything after one, up to the next,
#: is part of the same thing happening.
SPAN_STARTS = {
    "RoundStart", "TurnStart", "PowerUsed", "MoveStart", "OpportunityWindow",
}  # fmt: skip


def starts_span(event: Event) -> bool:
    return event.kind in SPAN_STARTS


def narrate_span(session: Session, events: list[Event]) -> str:
    """One sentence for one thing that happened.

    The page shows these and hides the raw event lines behind a checkbox, so
    this is the log a player actually reads. Composed from a span rather than
    per event because "rolled 19", "hit" and "took 5 damage" are three events
    and one sentence, and reading them as three is reading a transcript
    instead of a fight.
    """
    wire = session.wire
    if not events:
        return ""

    lines: list[str] = []
    damage: dict[int, int] = {}
    for event in events:
        d = event.wire()
        kind = event.kind
        if kind == "PowerUsed":
            lines.append(f"{wire.label(d['actor'])} uses {wire.power(d['power'])}")
        elif kind == "AttackRolled":
            lines.append(
                f"{wire.label(d['target'])}: {d['natural']}{d['bonus']:+d} "
                f"vs {d['vs'].upper()} {d['defence']}"
                + (" with combat advantage" if d.get("advantage") else "")
            )
        elif kind == "Hit":
            lines.append("critical hit!" if d.get("critical") else "hit")
        elif kind == "Miss":
            lines.append("miss")
        elif kind == "DamageApplied" and d["amount"]:
            damage[d["target"]] = damage.get(d["target"], 0) + d["amount"]
        elif kind in ("Healed", "TempHP") and d["amount"]:
            verb = "heals" if kind == "Healed" else "gains"
            what = "" if kind == "Healed" else " temporary hit points"
            lines.append(f"{wire.label(d['target'])} {verb} {d['amount']}{what}")
        elif kind == "ConditionApplied":
            lines.append(f"{wire.label(d['target'])} is {d['condition']}")
        elif kind == "ForcedMove":
            lines.append(f"{wire.label(d['target'])} is {d['how']}ed {d['squares']}")
        elif kind == "Bloodied":
            lines.append(f"{wire.label(d['actor'])} is bloodied")
        elif kind == "Dropped":
            lines.append(f"{wire.label(d['actor'])} goes down")
        elif kind == "Died":
            lines.append(f"{wire.label(d['actor'])} dies")
        elif kind == "SavingThrow":
            lines.append(
                f"{wire.label(d['actor'])} "
                + ("saves" if d["saved"] else f"fails a save ({d['natural']})")
            )
        elif kind == "ZoneCreated":
            lines.append(f"{wire.power(d['label'])} covers {len(d['squares'])} squares")
        elif kind == "MoveEnd":
            lines.append(f"{wire.label(d['actor'])} moves to {tuple(d['at'])}")
        elif kind == "TurnStart" and not d.get("ghost"):
            lines.append(f"{wire.label(d['actor'])}'s turn")
        elif kind == "OpportunityWindow":
            lines.append(
                f"{wire.label(d['actor'])} gets an opportunity attack on "
                f"{wire.label(d['provoker'])}"
            )
        elif kind == "EffectExpired":
            lines.append(f"{d['why']}: {d['what']}")

    for who, amount in damage.items():
        lines.append(f"{wire.label(who)} takes {amount}")
    return ", ".join(lines)


def narrate(session: Session, event: Event) -> str:
    """One readable line. Names, not ids; no rules meaning of its own."""
    wire = session.wire
    d = event.wire()

    def who(key: str) -> str:
        v = d.get(key)
        return wire.label(v) if isinstance(v, int) else "?"

    kind = event.kind
    if kind == "RoundStart":
        return f"Round {d['round']}"
    if kind == "TurnStart":
        return f"{who('actor')}'s turn" + (" (dead)" if d.get("ghost") else "")
    if kind == "TurnEnd":
        return ""
    if kind == "PowerUsed":
        return f"{who('actor')} uses {wire.power(d['power'])}"
    if kind == "AttackRolled":
        return (
            f"{who('attacker')} rolls {d['natural']}{d['bonus']:+d} = {d['total']} "
            f"vs {d['vs'].upper()} {d['defence']}"
            + (" (combat advantage)" if d.get("advantage") else "")
        )
    if kind == "Hit":
        return f"hit{' -- critical!' if d.get('critical') else ''}"
    if kind == "Miss":
        return "miss"
    if kind == "DamageApplied":
        tail = f" ({d['absorbed']} absorbed)" if d.get("absorbed") else ""
        return f"{who('target')} takes {d['amount']} damage{tail}, now on {d['hp']}"
    if kind == "Healed":
        return f"{who('target')} heals {d['amount']}, now on {d['hp']}"
    if kind == "TempHP":
        return f"{who('target')} gains {d['amount']} temporary hit points"
    if kind == "Bloodied":
        return f"{who('actor')} is bloodied"
    if kind == "Dropped":
        return f"{who('actor')} drops"
    if kind == "Died":
        return f"{who('actor')} dies"
    if kind == "ConditionApplied":
        return f"{who('target')} is {d['condition']} ({d['duration']})"
    if kind == "ConditionEnded":
        return f"{who('target')} is no longer {d['condition']} ({d['why']})"
    if kind == "SavingThrow":
        return (
            f"{who('actor')} saves: {d['natural']}{d['bonus']:+d} -- "
            + ("saved" if d["saved"] else "failed")
        )
    if kind == "MoveEnd":
        return f"{who('actor')} moves to {tuple(d['at'])}"
    if kind == "ForcedMove":
        return f"{who('source')} {d['how']}s {who('target')} {d['squares']}"
    if kind == "OpportunityWindow":
        return f"{who('actor')} gets an opportunity attack on {who('provoker')}"
    if kind == "ZoneCreated":
        return f"{wire.power(d['label'])} covers {len(d['squares'])} squares"
    if kind == "EffectExpired":
        return f"{who('actor')}: {d['what']} ends ({d['why']})"
    if kind == "Note":
        return d.get("text", "")
    return ""


def legal_for(session: Session) -> list[Action]:
    actor = session.current
    if actor is None:
        return []
    return legal(session.world, session.encounter, actor)


def is_down(session: Session, eid: int) -> bool:
    return is_(session.world, eid, Condition.DYING)


def has_gear(session: Session, eid: int) -> bool:
    return session.world.get(eid, Gear) is not None


def defences_of(session: Session, eid: int) -> Defenses:
    return session.world.need(eid, Defenses)


def all_candidates(session: Session, ref: str) -> list[int]:
    p = get(ref)
    actor = session.current
    if p is None or actor is None:
        return []
    return candidates(session.world, actor, p)


def aims(session: Session, ref: str) -> list:
    p = get(ref)
    actor = session.current
    if p is None or actor is None:
        return []
    return aim_points(session.world, actor, p)


def squares_of(session: Session, eid: int):  # noqa: ANN201
    return sorted(squares(session.world, eid))
