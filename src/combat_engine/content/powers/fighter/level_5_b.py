"""Fighter, level 5: the dailies the later books added.

Three shapes recur here.

**"You grant combat advantage to all attacks"** is not the relation, which
names one beneficiary: it is handed out from the interrupt window of each
attack's `AttackDeclared`, the last moment it can be given and still be
read, so an enemy that walks in later is covered too. That is
`paladin/level_1_b.py`'s `p13843` arrangement.

**"Once per round when ..."** is a latch on the round number held in a
closure, the way `paladin/marks.py` holds its once-a-round bite.

**A stance's riders** are `When.ENCOUNTER` and ended from `stance.on_end`,
because a second stance-clocked effect confuses `Effects.stance_of`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Keyword,
    Melee,
    TurnStart,
    When,
    Window,
    by_melee,
    leaves_me_out,
    power,
)
from combat_engine.engine.events import AttackDeclared, Hit, Miss, MoveEnd
from combat_engine.engine.query import adjacent, allies

from .footwork import ends_when_apart
from .grips import has_shield, heavy_rider, light_blade, reach_weapon, two_handed, two_melee

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL = [Keyword.MARTIAL]


def _open_to_everyone(c: Cast, *, until: When) -> Effect:
    """"You grant combat advantage to all attacks."

    The relation names one beneficiary, and who will swing is not known yet,
    so the opening is handed out from each attack's own declaration.
    """
    me = c.me

    def offer(ev: AttackDeclared) -> None:
        if ev.target == me and ev.attacker != me:
            c.grants_advantage(on=me, to=ev.attacker, until=When.EOT)

    return c.watch(
        AttackDeclared, offer, until=until, window=Window.BEFORE, on=me,
        label=f"{c.ref} wide open",
    )


def _basic_with_advantage(c: Cast, victim: int) -> None:
    """A melee basic attack that the printed line says has combat advantage."""
    c.grants_advantage(on=victim, to=c.me, until=When.EOT, once=True)
    c.basic(on=victim)


@power(
    "p10153",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10153(c: Cast) -> None:
    """The errata'd text: Melee weapon, and no reliable keyword.

    "Or until you end it as a free action" is a second ending nothing can
    reach -- there is no action for ending an ordinary effect -- so the
    trade runs to the end of the fight; see the report.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod + c.con_mod)
        c.push(2)
    if c.first:
        c.resist(5, on=c.me, until=When.ENCOUNTER)
        _open_to_everyone(c, until=When.ENCOUNTER)


@power(
    "p10493",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE, Keyword.WEAPON],
)
def p10493(c: Cast) -> None:
    """The stance and the riposte it unlocks share one printed id, so they
    are one row: the sub-power is an at-will immediate reaction, which comes
    to once a round, and that is the latch the watcher keeps.

    The free hand is the sub-power's Requirement rather than the stance's,
    so it is asked when the riposte fires and not when the stance is taken.
    """
    me = c.me
    stance = c.stance(label=c.ref)
    last: dict[str, int] = {}

    def riposte(ev: Miss) -> None:
        foe = ev.attacker
        if ev.target != me or not adjacent(c.world, me, foe):
            return
        if not by_melee(c.world, me, ev) or last.get("round") == c.world.round:
            return
        from .grips import hand_free

        if not hand_free(c.world, me) or not c.may("answer with a fist", who=me):
            return
        last["round"] = c.world.round
        if c.attack(c.str_, AC, on=foe):
            c.damage(c.w(1), c.str_mod, on=foe)
            c.grants_advantage(on=foe, to=me, until=When.EONT)

    held = c.watch(Miss, riposte, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p10495",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p10495(c: Cast) -> None:
    """"Cannot move on its turn if it was grabbed by you at the start of it"
    is asked once, at the start of the turn, and answered by pinning it for
    that turn -- which is what the sentence describes."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        me = c.me

        def check(ev: TurnStart) -> None:
            if ev.ghost or ev.actor != victim:
                return
            from .holds import grabbed_by

            if victim in grabbed_by(c):
                c.immobilized(on=victim, until=When.EOT)

        c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label=f"{c.ref} pin")
    else:
        c.damage(c.w(1), c.str_mod)
    c.prone()


@power(
    "p10496",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.STANCE, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p10496(c: Cast) -> None:
    """The printed range is Personal and the row still names a target and
    rolls a weapon, so it is written at melee reach.

    "As an immediate action or an opportunity action" -- only the second is
    on the event, so the watcher reads `opportunity`; an immediate basic
    attack cannot be told from an ordinary one. See the report.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    if victim is None:
        return
    me = c.me
    stance = c.stance(label=c.ref)

    def follow_up(ev: AttackDeclared) -> None:
        if ev.attacker != me or not getattr(ev, "opportunity", False):
            return
        if ev.target != victim or not c.wielding("two-weapon"):
            return
        if c.may("swing with the off-hand too", who=me):
            c.basic(on=victim)

    held = c.watch(
        AttackDeclared, follow_up, until=When.ENCOUNTER, window=Window.AFTER, on=me,
        label=c.ref,
    )
    stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p10497",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=has_shield,
    requires_text="needs a shield",
)
def p10497(c: Cast) -> None:
    """"Can use only basic attacks while you are adjacent to it" is the
    shape `c.cannot_attack` refuses with, narrowed: the declaration is
    turned away unless the row being used is what that creature's basic
    attack actually is."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    me = c.me
    hold = c.effect("only basic attacks", until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def refuse(ev: AttackDeclared) -> None:
        from combat_engine.engine import Powers

        if ev.attacker != victim or not adjacent(c.world, me, victim):
            return
        known = c.world.get(victim, Powers)
        allowed = {known.basic, known.opportunity} if known else set()
        if ev.power not in allowed:
            ev.cancel(c.ref)

    hold.subs.append(c.world.bus.on(AttackDeclared, refuse, window=Window.BEFORE, owner=me))


@power(
    "p12194",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, plus=4),
    requires=has_shield,
    requires_text="needs a shield",
)
def p12194(c: Cast) -> None:
    if c.strike():
        c.damage("3d10", c.str_mod)
    else:
        c.half_damage("3d10", c.str_mod)
    for foe in sorted(c.within(5, side="enemy")):
        if c.can_see(foe):
            c.mark(on=foe, until=When.EONT)


@power(
    "p12849",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p12849(c: Cast) -> None:
    """The bystanders are read before the target is thrown anywhere: "each
    enemy adjacent to the target" is where it was standing when it was hit.
    """
    victim = c.target
    if victim is None:
        return
    around = sorted(e for e in c.within(1, of=victim, side="enemy") if e != victim)
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.push(3)
        c.prone()
    else:
        c.half_damage(c.w(2), c.str_mod)
        c.push(1)
    for foe in around:
        c.flat(c.str_mod, on=foe)
        c.push(1, on=foe)


@power(
    "p2470",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=light_blade,
    requires_text="needs a light blade",
)
def p2470(c: Cast) -> None:
    """"Save ends both" is one effect with the burn hung on it, or the
    target gets two saving throws against a thing the book says is one."""
    c.shift(1)
    if c.strike():
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS,
            ongoing=(10 + c.dex_mod, DamageType.UNTYPED),
        )
    else:
        c.ongoing(max(1, c.dex_mod))
    c.shift(1)


@power(
    "p4231",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4231(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p4322",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4322(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod + (c.dex_mod if c.wielding("flail") else 0))
        c.condition(Condition.DAZED, Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod + (c.dex_mod if c.wielding("flail") else 0))


@power(
    "p4323",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4323(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    me = c.me
    last: dict[str, int] = {}

    def join_in(ev: Hit) -> None:
        if ev.target != victim or ev.attacker == me or ev.attacker not in allies(c.world, me):
            return
        if not by_melee(c.world, me, ev) or last.get("round") == c.world.round:
            return
        if not adjacent(c.world, me, victim) or not c.may("pile in", who=me):
            return
        last["round"] = c.world.round
        _basic_with_advantage(c, victim)

    c.watch(Hit, join_in, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p4324",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires_text="must charge with this in place of the basic attack",
    charges=True,
)
def p4324(c: Cast) -> None:
    """A row whose printed Requirement is the charge: the flag goes up by
    hand and `c.run_at` walks, because `c.charge_at` would reach the swing
    through `use` and `use` refuses a row already in flight."""
    victim = c.target
    if victim is None:
        return
    c.charge = True
    try:
        c.run_at(victim)
        if c.strike(on=victim):
            c.damage(c.w(3), c.str_mod + c.con_mod, on=victim)
        else:
            c.half_damage(c.w(3), c.str_mod + c.con_mod, on=victim)
    finally:
        c.charge = False


@power(
    "p4325",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
    requires=reach_weapon,
    requires_text="needs a reach weapon",
)
def p4325(c: Cast) -> None:
    """Two printed triggers for the same answer -- shifting away, and
    swinging at anybody else -- so both are watched. "An attack that doesn't
    include you" is judged over the whole attack with `leaves_me_out`, not
    off one announcement.

    The eladrin rider is a race the engine does not have; see the report.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.push(1)
    me = c.me

    def answer() -> None:
        if not c.may("step in and swing", who=me):
            return
        c.shift(1)
        if adjacent(c.world, me, victim):
            c.basic(on=victim)

    def on_shift(ev: MoveEnd) -> None:
        if ev.actor == victim and ev.kind_ == "shift":
            answer()

    def on_swing(ev: AttackDeclared) -> None:
        if ev.attacker == victim and leaves_me_out(c.world, me, ev):
            answer()

    c.watch(MoveEnd, on_shift, until=When.ENCOUNTER, on=me, label=f"{c.ref} step")
    c.watch(
        AttackDeclared, on_swing, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} swing",
    )


@power(
    "p4326",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4326(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(1), c.str_mod + heavy_rider(c))
        ends_when_apart(c, c.immobilized(until=When.ENCOUNTER), victim)
    else:
        c.half_damage(c.w(1), c.str_mod + heavy_rider(c))
        c.immobilized(until=When.EONT)


@power(
    "p9365",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE, Keyword.WEAPON],
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p9365(c: Cast) -> None:
    """A printed choice each time it fires: the off-hand at somebody else,
    or a step and a moment's cover."""
    me = c.me
    stance = c.stance(label=c.ref)
    last: dict[str, int] = {}

    def payout(ev: Hit) -> None:
        if ev.attacker != me or last.get("round") == c.world.round:
            return
        if not by_melee(c.world, me, ev):
            return
        others = sorted(e for e in c.within(1, side="enemy") if e != ev.target)
        last["round"] = c.world.round
        if others and c.may("swing with the off-hand", who=me):
            c.basic(on=c.choose(others, "who the off-hand catches"))
            return
        c.shift(1)
        c.bonus(AC, 2, on=me, until=When.SONT)
        c.bonus(REF, 2, on=me, until=When.SONT)

    held = c.watch(Hit, payout, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p9366",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p9366(c: Cast) -> None:
    """Three swings, each at a creature the last two did not catch, with a
    step between them. Both follow-ups are Effect lines."""
    struck = {c.target}
    if c.strike():
        c.damage(c.w(1), c.str_mod + c.dex_mod)
    c.shift(1)
    pool = sorted(e for e in c.within(1, side="enemy") if e not in struck)
    second = c.choose(pool, "who the off-hand catches") if pool else None
    if second is None:
        return
    struck.add(second)
    if c.attack(c.str_ + 1, AC, on=second):
        c.damage(c.w(1, hand="off"), c.dex_mod, on=second)
    c.shift(1)
    pool = sorted(e for e in c.within(1, side="enemy") if e not in struck)
    third = c.choose(pool, "who both blades catch") if pool else None
    if third is not None and c.attack(c.str_ + 1, AC, on=third):
        c.damage(c.w(1), c.str_mod, on=third)


@power(
    "p9996",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_handed,
    requires_text="needs a two-handed weapon",
)
def p9996(c: Cast) -> None:
    """Shove it away and run it down. `c.charge_at` is a different row from
    this one, so `use` lets it through; whether its swing landed is read off
    the log rather than guessed from the return."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    c.push(3)
    me = c.me
    landed: list[int] = []

    def note(ev: Hit) -> None:
        if ev.attacker == me and ev.target == victim:
            landed.append(ev.seq)

    watching = c.world.bus.on(Hit, note, owner=me)
    try:
        c.charge_at(victim)
    finally:
        c.world.bus.off(watching)
    if landed:
        c.flat(c.con_mod, on=victim)
        c.prone(on=victim)
