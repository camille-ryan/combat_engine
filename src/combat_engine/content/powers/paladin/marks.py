"""The paladin's second mark, shared by the two dozen rows that print it.

Later books give the paladin a mark it can hand out in passing -- a rider on
an attack rather than an action of its own. It holds like any mark and, on
top of that, bites for radiant damage the first time each round the marked
creature attacks without the paladin among the targets. That is the same
arrangement `p805` installs and with the same numbers; a bare `c.mark()` is
the half of it that costs nothing, and writing the watcher out per row would
be two dozen chances to get the once-a-round latch wrong.

`hold` hangs the whole thing on an effect that already exists, for the rows
printing "ongoing damage and <the mark> (save ends both)": two effects would
be two saving throws against a thing the book says is one.
"""

from __future__ import annotations

from combat_engine.engine import (
    Cast,
    DamageType,
    Effect,
    Relation,
    When,
    leaves_me_out,
)
from combat_engine.engine.events import AttackDeclared

#: Every row that has laid a divine sanction, by ref.
#:
#: The sanction's bite is dealt by `c.flat` inside `burning_mark`, which stamps
#: the **calling** row's ref onto the blow -- so `DamageApplied.detail` names
#: whichever of two dozen rows laid it, and a card saying "radiant damage from
#: your divine sanction" had no single ref to test against. This is that set.
#:
#: Filled as marks are laid rather than declared up front, which is sound in
#: the only order that matters: the bite cannot arrive before the mark that
#: deals it, so a ref is always registered by the time its damage is seen.
SANCTIONS: set[str] = set()


def burning_mark(
    c: Cast,
    *,
    on: int | None = None,
    until: When = When.EONT,
    hold: Effect | None = None,
) -> Effect | None:
    """Mark a creature, and make attacking anybody else cost it."""
    who = c.target if on is None else on
    if who is None:
        return None
    me = c.me
    SANCTIONS.add(c.ref)
    struck: dict[int, int] = {}

    def bite(ev: AttackDeclared) -> None:
        # "An attack that does not include you" is judged over the whole
        # attack rather than this one announcement: a burst that caught the
        # paladin would otherwise pay out off one of its other targets.
        if ev.attacker != who or not leaves_me_out(c.world, me, ev):
            return
        if struck.get(who) == c.world.round:
            return  # the first time each round, and no more
        struck[who] = c.world.round
        # **f2909 swaps which modifier this pays, and only upward.** #550:
        # the clause belongs in the body it names rather than in the feat.
        # The printed "you can" is a choice worth making, so the swap is
        # taken where it is not a downgrade -- `f2128` in `feats/paladin_b.py`
        # reads the same word the same way, and `souls._resilience` is the
        # precedent for an optional "in place of" paying the difference and
        # nothing else. `c.credit`, or the blow is the laying row's alone --
        # `audit._dealt_by` reads that field beside `detail`, so both the row
        # and the feat are credited and neither loses the damage.
        if c.feat("f2909") and c.str_mod > c.cha_mod:
            with c.credit("f2909"):
                c.flat(3 + c.str_mod, dtype=DamageType.RADIANT, on=who,
                       from_attack=False)
            return
        c.flat(3 + c.cha_mod, dtype=DamageType.RADIANT, on=who, from_attack=False)

    if hold is None:
        held = c.mark(until=until, on=who)
        c.watch(AttackDeclared, bite, until=until, on=me, label=f"{c.ref} mark")
        out: Effect | None = held
    else:
        # `via=c.ref` because this branch bypasses `durations._install_state`,
        # which is where every other mark gets its provenance from `eff.by`. A
        # paladin's challenge left unlabelled here would read as "laid by no
        # row", and `i531p1` asks exactly this question of exactly this mark.
        # #875.
        c.world.relations.set(Relation.MARKED_BY, me, who, via=c.ref)
        hold.relations.append((Relation.MARKED_BY, me, who))
        hold.subs.append(c.world.bus.on(AttackDeclared, bite, owner=me))
        out = hold
    _slide_on_the_mark(c, me, who)
    return out


def _slide_on_the_mark(c: Cast, me: int, who: int) -> None:
    """f3083: "an enemy adjacent to you" is slid 1 the moment it is marked.

    **Written here because this helper is the single door** every divine
    sanction in the tree goes through -- 22 call sites across nine files --
    so one clause covers every row that lays one, which is what the card
    says and what a per-row copy would get wrong twenty-two times. #550
    puts a feat's clause in the body it names; the body here is shared.

    Two things the next reader needs:

    * **`p11049` lays its sanction with a bare `c.mark()`** rather than
      through this helper, so it is the one sanction this clause misses.
      That is a pre-existing inconsistency in that row and not this
      clause's to fix -- recorded rather than papered over.
    * The adjacency is measured **from the caster**, which is what
      `c.adjacent` does, and at the moment the mark lands. A free action
      costs nothing the engine tracks, so the printed action line needs
      no verb.
    """
    if not c.feat("f3083") or not c.adjacent(who):
        return
    if not c.may("slide the marked enemy 1 square", who=me):
        return
    with c.credit("f3083"):
        c.slide(1, on=who)
