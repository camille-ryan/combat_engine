"""Paladin feats.

Most of these name the power they ride on **by ref** in their own
prerequisite or their benefit, so they are ordinary `PowerUsed` riders.
Two shapes needed more than that and both turned out to be reachable:

* "a cf:paladin-f0 power" is not a set anybody recorded, but it does not
  have to be -- every row that spends the allowance carries
  `group=CHANNEL_DIVINITY`, which is how `dsl._group_spent` holds the
  once-a-fight limit. Reading the group off the used row is the same
  question the engine already asks.
* A saving throw is announced with `against` set to the effect's own
  `str`, which begins with the effect's id -- so the hold being shaken
  off can be found again, and `durations.keywords_of` answers what the
  row that laid it was made of.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    Ability,
    ActionType,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    PowerUsed,
    SavingThrow,
    Trigger,
    When,
    Window,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.dsl import get
from combat_engine.engine.durations import keywords_of


def _i_used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _i_channelled(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A power of mine that spends the once-a-fight allowance."""
    row = get(ev.power)
    return ev.actor == me and row is not None and row.group == CHANNEL_DIVINITY


def _melee(ctx: dict[str, Any]) -> bool:
    """Read off the row's own reach line, which both contexts carry as
    `power`. `ctx["ranged"]` is only on the attack side."""
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind == "melee"


def _tier(level: int) -> int:
    return 1 if level < 11 else (2 if level < 21 else 3)


#: Which characters have already had their surge pool raised. A trait is
#: armed once per encounter and the raise is once per *character*, so
#: without this a paladin gains a surge every fight of the day.
_RAISED: dict[tuple[int, int], bool] = {}


@power("f290", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1566",
       on=Trigger(PowerUsed, _i_used("p1566"), "you use p1566"))
def f290(c: Cast) -> None:
    """Extra hit points for whoever that power was aimed at. `ev.targets`
    is trustworthy on `PowerUsed` -- targets are chosen before the body
    runs, even though what the body does is not yet known."""
    for who in c.trigger.targets:
        c.heal(c.cha_mod, on=who)


@power("f1512", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1512(c: Cast) -> None:
    """The healing half rides on the same ref as f290.

    The other half -- one more healing surge a day -- is `Health`'s
    ceiling, which it carries as `max_surges`, so the pool is raised and
    the extra surge handed over in the same breath. Latched per character
    rather than done each time the trait arms: the sentence is about the
    character sheet and a trait is armed at the start of every fight.
    """
    c.grant_row("f290", on=c.me, until=When.ENCOUNTER)
    key = (id(c.world), c.me)
    health = c.world.get(c.me, Health)
    if health is None or _RAISED.get(key):
        return
    _RAISED[key] = True
    health.max_surges += 1
    c.regain_surge(1, on=c.me)


@power("f1086", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p805 on an undead creature",
       on=Trigger(PowerUsed, _i_used("p805"), "you use that power"))
def f1086(c: Cast) -> None:
    """Radiant damage when this character marks an undead creature.

    The mark is not watched for -- the card names the row that lays it,
    and a row being *used* is announced. `PowerUsed` fires above p805's
    body, which does not matter here: its targets are chosen first, and
    what the sentence turns on is what the creature is rather than what
    the mark did.

    `usage=AT_WILL` because p805 is an at-will and nothing on this card
    limits how often it pays; declared `ENCOUNTER`, a triggered trait
    fires once a fight (#210).
    """
    for foe in c.trigger.targets:
        if "undead" in c.kinds_of(foe):
            c.flat(2 * _tier(c.level), dtype=DamageType.RADIANT, on=foe)


@power("f1091", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1091(c: Cast) -> None:
    c.grant_row("f1091b", on=c.me, until=When.ENCOUNTER)


@power("f1091b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
       attack=Attack(Ability.CHA, vs=REF))
def f1091b(c: Cast) -> None:
    """A surge spent for damage rather than healing, so `c.spend_surge`
    and not `c.surge` -- the second would heal the caster, which is the
    one thing the card says does not happen."""
    if not c.is_kind("undead"):
        return
    if c.strike().hit and c.spend_surge(on=c.me):
        c.flat(c.surge_value(), dtype=DamageType.RADIANT)


def _shaken_off(c: Cast, against: str):  # noqa: ANN202
    """The effect a `SavingThrow` was rolled against, or None.

    `Durations.save` sets `against` to `str(eff)`, which opens with the
    effect's own id -- so the hold is findable again, and the interrupt
    window is early enough that it is still live. Nothing else on the
    event says what was being shaken off.
    """
    head = against[1:].split("[", 1)[0] if against.startswith("e") else ""
    return c.world.effects.live.get(int(head)) if head.isdigit() else None


@power("f1088", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1088(c: Cast) -> None:
    """Resist necrotic for whoever p1746 was aimed at, when they shake a
    necrotic hold off.

    Two things had to be found rather than read. Who the power touched is
    latched off `PowerUsed` -- p1746's targets are chosen before its body
    and are the printed set. What the saving throw was *against* is the
    effect itself, recovered from `ev.against`; its keywords come from
    `durations.keywords_of`, which reads them off the row named in the
    label, and an ongoing burn is asked separately because a burn that
    imposes no condition carries its type and no keyword at all.

    `Window.BEFORE`, because a successful save ends the hold and the
    effect is gone from the live register by the reaction window.
    """
    me = c.me
    touched: set[int] = set()

    def on_use(ev: Any) -> None:
        if ev.actor == me and ev.power == "p1746":
            touched.update(ev.targets)

    def on_save(ev: SavingThrow) -> None:
        if ev.actor not in touched or not ev.saved:
            return
        hold = _shaken_off(c, ev.against)
        if hold is None:
            return
        burn = hold.ongoing_types or ((hold.ongoing[1],) if hold.ongoing else ())
        if Keyword.NECROTIC in keywords_of(hold.label) or DamageType.NECROTIC in burn:
            c.resist(c.cha_mod, DamageType.NECROTIC, on=ev.actor, until=When.EONT)

    c.watch(PowerUsed, on_use, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(SavingThrow, on_save, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)


@power("f1497", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2483 or p2484",
       on=(
           Trigger(PowerUsed, _i_used("p2483"), "you use p2483"),
           Trigger(PowerUsed, _i_used("p2484"), "you use p2484"),
       ))
def f1497(c: Cast) -> None:
    """Both racial powers are named by ref, so both halves of the printed
    "or" are declared -- `on=` takes a sequence and declaring one of two
    looks finished."""
    c.bonus(
        "damage", c.wis_mod, on=c.me, until=When.EONT,
        when=lambda ctx: not ctx.get("ranged", False),
    )


@power("f1502", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a cf:paladin-f0 power",
       on=Trigger(PowerUsed, _i_channelled, "you use one of those powers"))
def f1502(c: Cast) -> None:
    """Which rows belong to the feature *is* recorded -- as `group=`.

    Every row that spends the allowance carries `CHANNEL_DIVINITY` so
    that `dsl._group_spent` can refuse the second one in a fight, and
    that string is the set this card names. Read off the used row rather
    than hand-listed, so a row added later is in it.

    "Power bonus" is the printed word, and `once=True` spends it on the
    next melee roll, which is what "your next melee attack roll" says.
    """
    c.bonus("attack", 1, kind="power", on=c.me, until=When.EONT,
            once=True, when=_melee)
