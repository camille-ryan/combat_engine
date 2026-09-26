"""The wizard's spellbook.

`Powers.owned` is what a character holds and has not prepared, and this is
the row that turns owning into preparing. `chargen.spellbook` stocks the
book off the class chassis -- two rows per slot, which is what the feature
gives -- and the wizard arrives with one of each pair already prepared.

**The judgement.** Preparing happens after an extended rest and the engine
has no rest, so it happens when the fight starts, which is the same moment
for everything that reads it. Arming a trait is the only hook there is and
it is the right one: what the feature decides is which powers the wizard
walks in holding.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Keyword,
    Powers,
    Usage,
    get,
    power,
)


@power(
    "cf:wizard-spellbook",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def wizard_spellbook(c: Cast) -> None:
    """One daily and one utility out of the book, into a slot standing empty.

    **It does not swap a prepared power for an equivalent one.** The slot
    count never changes, so a swap has to prefer one row over another and
    the engine has no way to; re-preparing every fight would be churn
    dressed as a feature. What the feature is for is that the book exists
    and is reachable -- `p7377` is the row that reaches into it mid-fight,
    and `chargen.spellbook` is what stocks it off the chassis.
    """
    book = c.spellbook()
    known = c.world.get(c.me, Powers)
    if not book or known is None:
        return
    for slot in (Usage.DAILY, Usage.ENCOUNTER):
        options = [ref for ref in book if (p := get(ref)) is not None and p.usage is slot]
        prepared = [
            ref
            for ref in known.known
            if (p := get(ref)) is not None and p.usage is slot and p.level > 0
        ]
        if not options or prepared:
            continue
        pick = c.choose(options, f"cf:wizard-spellbook: which {slot.value} to prepare")
        if pick is not None:
            c.prepare(pick)
