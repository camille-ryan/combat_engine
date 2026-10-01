"""What a character should take, ranked, with the reasons kept.

Every build choice in this package was uniform random or fixed: a race drawn
from all 46 with `rng.choice`, a feat drawn from ~411 legal ones the same way,
and a weapon that came with the build leg and never changed. Nothing preferred
a race whose ability bonuses suit the class, and nothing knew that a feat
spent on a weapon is worth more to a fighter than to a wizard.

**Two callers want the same numbers for different reasons**, which is what
decides the shape here:

* the **dealer** -- `deal_race`, `feats_for`, `outfit` -- needs to choose
  without a human, for a fight nobody is watching;
* the **advisor** -- `api/` and the chargen page -- needs to rank the options
  and say *why*, and never chooses anything.

So scoring and choosing are separate: `*_options` returns every candidate with
its score and the named terms that made it, and `sample` is the only thing that
picks. The advisor calls the first and stops.

That is `engine/policy.py`'s shape on purpose. Its `features()` returns a flat
dict of named numbers and `WEIGHTS` prices each one, so an explanation is just
the terms -- and a weight with a comment beside it is a design decision somebody
can argue with. This file is the same arrangement for build choices rather than
for actions in a fight.

**Ranked, then sampled -- never argmax.** `deal_race`'s own docstring makes the
argument: "a draw that always took the best pair would make every fighter the
same two races", and a player picks for flavour at least as often as for the
numbers. Scoring says which choices are good; sampling keeps them from being
the only ones.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from combat_engine.engine.components import Weapon

    from . import Build


@dataclass(frozen=True)
class Choice:
    """One candidate, its score, and what the score was made of.

    `ref` is a ref and never a name -- `r3`, `f1252`, `w:spiked-chain`. The
    advisor turns it into something readable through the same `wire` the fight
    page uses, which is what keeps `CE_NAMES=off` honest.

    `terms` holds contributions that are **already weighted**, so they sum to
    `score` and a reader does not have to know the weights table to read them.
    Zero terms are left out: a list of every term that did not apply is noise
    in a tooltip.
    """

    ref: str
    score: float
    terms: dict[str, float]

    @property
    def why(self) -> list[tuple[str, float]]:
        """The terms, largest contribution first. What a tooltip shows."""
        return sorted(self.terms.items(), key=lambda kv: (-abs(kv[1]), kv[0]))


#: What each term is worth. Every entry carries the reason, because a weight
#: with no argument behind it is a number nobody can check -- and because these
#: are the numbers Camille will want to move after reading a few sheets.
WEIGHTS: dict[str, float] = {
    # -- a race -----------------------------------------------------------
    # The whole point of a race for a build: +2 where the class attacks from
    # is a point of attack and a point of damage on nearly every row it owns.
    "primary_bonus": 6.0,
    # Worth real value and not half: a secondary drives the fork's own rows,
    # and several classes gate a feature on it.
    "secondary_bonus": 3.5,
    # A racial power that actually attacks is a free encounter power. One that
    # does not is counted by `traits_written` instead.
    "grants_attack_row": 2.0,
    # Each finished trait is a small standing benefit. Deliberately small: a
    # race with four written traits is not four times better than one with one.
    "traits_written": 0.6,
    # A surge is a second wind's worth of hit points over a fight.
    "surges": 1.5,
    # Squares of speed past the common 6.
    "speed_above_six": 1.0,
    # Going earlier is worth about a third of a point of attack.
    "initiative": 0.4,
    # -- a feat -----------------------------------------------------------
    # `_leans_on` reads the row's own source for `c.<ability>_mod`, so this is
    # "does the feat pay out through the ability this build is good at". It
    # returns 0, 1 or 2 and is the closest thing to fitness the package had.
    "leans_on_build": 4.0,
    # Opening a weapon up is worth having **if the character swings one**.
    "opens_a_weapon": 3.0,
    # The reason #209 exists. A superior weapon is the interesting half of the
    # weapon table -- 57 of 117 -- and unreachable without a feat, so a feat
    # that reaches one is worth more than one that reaches a military weapon
    # the chassis might have dealt anyway.
    "weapon_is_superior": 4.0,
    # **The wizard exclusion, as a term rather than a special case.** A build
    # whose chassis is implements only has nothing to do with a weapon feat,
    # and the honest way to say so is to price it rather than to filter it:
    # a cleric carries a mace *and* a holy symbol and is a real candidate,
    # which a filter on "is a caster" would get wrong.
    "implement_only_build": -9.0,
    # A feat that hands over a card is a power slot for a feat slot.
    "grants_a_row": 3.0,
    # Feats chain. Taking one that others need is worth something even when
    # its own benefit is thin, and this is what lets a career reach the
    # feat at the end of a chain.
    "unlocks_other_feats": 0.8,
    # A `dropped=` feat plays with a clause missing, so it is worth less than
    # a finished one and more than nothing. A `todo=` feat is refused in play
    # and is not a candidate at all -- `feats_for` already excludes those.
    "carries_a_marker": -3.0,
    # Declared finished and inert in a fight. Fine for a character and no use
    # to a fight being analysed, which is what the dealer is for.
    "out_of_combat": -5.0,
    # -- which weapon is actually held ------------------------------------
    # **Camille's rule**: "If the character has taken the feat, it should
    # almost certainly be taking that weapon as well." Heavy enough to beat
    # the chassis weapon's die and light enough that `keeps_class_rows` can
    # still stop it, which is the one case where taking it is wrong.
    "spent_a_feat": 10.0,
    # `outfit`'s docstring names the trap this answers: swing whichever hits
    # hardest and a rogue puts its dagger away, taking every light-blade
    # Requirement its own class rows are written against with it. So count
    # them -- one point per row of the character's own that would still work.
    "keeps_class_rows": 3.0,
    # Average damage of the printed expression, mildly better when higher.
    # Small on purpose: this is the term that, left large, produces exactly
    # the mistake above.
    "damage_die": 0.5,
    # A property the rows care about.
    "high_crit": 1.0,
    "versatile": 0.5,
    "reach_weapon": 1.5,
    # -- what somebody who played the class thought ------------------------
    # From `ratings.py`, read out of 37 community guides.
    #
    # **Centred on black, so an average rating adds nothing.** The value fed in
    # is `score - 3.0`, giving -3.0 for a red and +3.0 for a gold, weighted here
    # to +-3.6. Two reasons, and the first was a measured mistake:
    #
    # Fed in raw, the term added 3.6 to 7.2 to *43 of 46 races* -- and a
    # gold-rated race with no primary-ability bonus then outranked a
    # black-rated race that had one, because 7.2 beats `primary_bonus` at 6.0.
    # The party's hit rate fell from 63% to 57% and the fighter's from 64% to
    # 50%. A guide rates a race for the whole class, including utility and
    # defences; it must not be able to outweigh the one term that is worth a
    # point of attack and a point of damage on every row.
    #
    # And a term that is positive almost everywhere is not a preference, it is a
    # constant: it compresses the spread `sample` weights by and pushes the draw
    # back toward uniform, which is the opposite of the intent.
    #
    # **Only applied when a guide actually rated it.** An unrated option gets
    # no term at all rather than the 2.5 placeholder, because a made-up number
    # competing with measured terms is worse than an absent one. 72% of written
    # heroic rows are rated, but that runs from 93% for a fighter to 24% for a
    # monk, so the term is present far more often for some classes than others.
    "guide_rating": 1.2,
}

#: Every legal option keeps a floor of chance, so nothing is unreachable.
#:
#: **A floor alone does not work on a large pool, and that arithmetic is worth
#: writing down.** With 411 legal feats, a floor of 1 gives the also-rans 410
#: units of weight between them against perhaps 20 for the best option, so the
#: best is drawn about 5% of the time and the draw is barely better than
#: uniform. `sample` takes a `top` for that reason: concentrate on the
#: plausible options, then keep variety *inside* them. A pool of 46 races needs
#: no such help.
FLOOR = 1.0

#: How many candidates a feat draw considers. Wide enough that two characters
#: of the same class rarely take the same feat, narrow enough that what they
#: take is a feat somebody would have picked on purpose.
FEAT_TOP = 24

#: `race_options` per (class, leg). The ranking is the same every time it is
#: asked and it costs **41ms**, nearly all of it inside `RaceLine.granted`,
#: which scans the whole 12,197-row registry for each of the 46 races to find
#: their traits. That is 560,000 prefix tests per character built.
_RACES: dict[tuple[str, str, bool], list[Choice]] = {}


def _use_ratings() -> bool:
    """Read the package flag at call time, not at import.

    `from . import USE_RATINGS` at module level would freeze the value, and
    `scripts/winrate.py` flips it between runs inside one process.
    """
    from . import USE_RATINGS

    return USE_RATINGS


def _rating_term(ref: str, cls: str) -> dict[str, float]:
    """The guide term, or nothing at all when nobody rated it."""
    if not _use_ratings():
        return {}
    from combat_engine.ratings import rated, score

    if not rated(ref, cls):
        return {}
    from . import BLACK

    return {"guide_rating": score(ref, cls) - BLACK}


def _pays_off_through(declared) -> set[str]:  # noqa: ANN001
    """Which abilities a row's own body reads a modifier from.

    Same reading `chargen._leans_on` does and for the same reason -- "a body
    saying `c.int_mod` needs Intelligence and no header field says so" -- but
    returning the set rather than a count, because the question here is whether
    an option pays off through an ability this build has dumped.
    """
    import inspect

    from combat_engine.engine.types import Ability

    try:
        body = inspect.getsource(declared.body)
    except (OSError, TypeError):
        return set()
    return {a.value for a in Ability if f"c.{a.value}_mod" in body}


def _on_a_dump_stat(declared, leg: Build) -> bool:  # noqa: ANN001
    """Does this option pay off *only* through an ability the build dumped?

    Camille's rule, and the strictest of the three readings considered: an
    option is refused when the abilities it pays off through are all outside the
    build's primary and secondary.

    It matters most for the nineteen classes whose legs draw from one power pool
    and differ only on the **secondary** -- for those, the other leg's secondary
    is your dump stat. An artificer with Constitution second should not be handed
    the Wisdom-payoff options, which is exactly the distinction one guide drew by
    colouring the two halves of a name differently.

    A row that reads no modifier at all is not refused: it pays off through
    something else and there is no dumped ability to object to.
    """
    named = _pays_off_through(declared)
    if not named:
        return False
    keep = {leg.primary.value}
    if leg.secondary is not None:
        keep.add(leg.secondary.value)
    return named.isdisjoint(keep)


def _priced(raw: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Weight a raw term dict, drop what did not apply, and total it."""
    terms = {
        name: WEIGHTS[name] * value
        for name, value in raw.items()
        if value and name in WEIGHTS
    }
    return sum(terms.values()), terms


def _ranked(scored: list[Choice]) -> list[Choice]:
    """Best first, ties broken on the ref so a run is reproducible."""
    return sorted(scored, key=lambda c: (-c.score, c.ref))


def swings_a_weapon(cls: str, build: Build | None = None) -> bool:
    """Does this build fight with a weapon at all?

    Read off the chassis rather than off a list of caster classes, because the
    interesting case is the one a list gets wrong: a cleric carries a mace
    *and* a holy symbol, so it is both, and a weapon feat is a real choice for
    it. Only a build whose arms are implements outright is excluded.
    """
    from . import CLASSES, build_of

    line = CLASSES.get(cls)
    if line is None:
        return True
    arms = (build or build_of(cls)).weapons or line.weapons
    return any(w.group != "implement" for w in arms)


def race_options(cls: str, level: int = 1, build: Build | None = None) -> list[Choice]:
    """Every race, ranked for this class and leg.

    Cached on (class, leg) -- see `_RACES`. `level` is not part of the key
    because nothing here reads it yet; it is in the signature because the
    advisor will want it the moment a race's value depends on tier, and
    adding it then is a key change rather than a signature change.
    """
    from combat_engine.engine.dsl import REGISTRY

    from . import RACES, build_of

    leg = build or build_of(cls)
    # **`USE_RATINGS` is part of the key.** Without it the first mode to run
    # poisons the cache for the second, and `scripts/winrate.py` runs both in
    # one process -- so a before/after comparison would silently compare a mode
    # against itself.
    key = (cls, leg.name, _use_ratings())
    if key in _RACES:
        return list(_RACES[key])
    out: list[Choice] = []
    for ref, race in sorted(RACES.items()):
        raised = race.taken(leg)
        rows = [r for r in race.granted() if r in REGISTRY]
        score, terms = _priced(
            {
                "primary_bonus": float(leg.primary in raised),
                "secondary_bonus": float(leg.secondary in raised),
                "grants_attack_row": float(
                    any(REGISTRY[r].is_attack for r in rows)
                ),
                "traits_written": float(
                    sum(1 for r in rows
                        if not REGISTRY[r].todo and not REGISTRY[r].obsolete)
                ),
                "surges": float(race.surges),
                "speed_above_six": float(max(0, race.speed - 6)),
                "initiative": float(race.initiative),
                **_rating_term(ref, cls),
            }
        )
        out.append(Choice(ref=ref, score=score, terms=terms))
    _RACES[key] = _ranked(out)
    return list(_RACES[key])


#: `_prerequisite_counts`, worked out once. **Measured, not tidied.** It reads
#: every feat's gate out of the database and parses 2,077 JSON trees, and it
#: was being called once per feat slot -- so once per character, so once per
#: row for the audit, which builds a character each time. Uncached, scoring
#: took a character from 27ms to 187ms and put **half an hour** on a full
#: `audit.py` run, an instrument whose cost `scripts/CLAUDE.md` says is
#: already the thing most likely to make this project unpleasant.
_PREREQS: dict[str, int] | None = None

#: `_leans_on` per (ref, leg). It reads the row's **source** with `inspect`,
#: 411 times per feat draw. Same story as above and the larger half of it.
_LEANS: dict[tuple[str, str], int] = {}

#: `_hands_over_a_row` per ref -- another `inspect.getsource` per candidate,
#: and it was missed on the first pass at this: caching only `_leans_on` took
#: a character from 187ms to 116ms and the second read was most of what was
#: left.
_GRANTS: dict[str, bool] = {}



def _prerequisite_counts() -> dict[str, int]:
    """How many feats name each ref in their own gate.

    Read off the gates rather than kept beside them, for the reason the rest
    of this package reads the registry: a list would go stale the next time a
    feat landed. Cached because the registry does not change while a process
    runs -- see `_PREREQS`.
    """
    global _PREREQS

    if _PREREQS is not None:
        return _PREREQS
    from combat_engine.etl.build import game

    counts: dict[str, int] = {}

    def walk(node: dict | None) -> None:
        if not node:
            return
        for branch in (node.get("all") or []) + (node.get("any") or []):
            walk(branch)
        named = node.get("ref")
        if named:
            counts[named] = counts.get(named, 0) + 1

    for row in game().execute("SELECT prereq FROM feat WHERE prereq != ''"):
        walk(json.loads(row["prereq"]) if row["prereq"] else None)
    _PREREQS = counts
    return counts


#: Every feat's printed gate, parsed once. The query and 2,077 JSON trees are
#: the same on every call and `feats_for` asks per slot.
_GATES: dict[str, dict | None] | None = None


def feat_gates() -> dict[str, dict | None]:
    """Every feat ref, mapped to its printed prerequisite tree."""
    global _GATES

    if _GATES is None:
        from combat_engine.etl.build import game

        _GATES = {
            row["ref"]: (json.loads(row["prereq"]) if row["prereq"] else None)
            for row in game().execute("SELECT ref, prereq FROM feat")
        }
    return _GATES


def legal_feats(
    cls: str,
    level: int = 1,
    build: Build | None = None,
    race: str = "",
    taken: Sequence[str] = (),
) -> list[str]:
    """The feats this character could actually take.

    One pool, and both the dealer and the advisor draw from it: the advisor
    has to rank exactly what the dealer could have taken, and a second copy of
    "written, not `todo`, gate met" is a second thing to go stale. It went
    stale immediately -- see below.

    **A second card is not a feat.** `f1091b` is the card `f1091` hands over,
    minted by the importer because the parent's columns are wrong for it, and
    it sits in the `feat` table like any other row. Offered as a choice it is
    wrong twice: the character cannot take it (it comes *with* something), and
    it is shown under the granted power's name rather than the feat's -- which
    is how this was noticed, a card's name displayed where a feat's belonged.

    **210 of the 405 rows a level-1 fighter was offered were second cards**,
    and for 209 of them the feat that grants the card was not itself in the
    list. `loadout` has always excluded them from the *power* pool for exactly
    this reason; the feat pool never did, so **the dealer has been handing
    them out as feats all along** -- 22 of 40 dealt fighters before any of this
    session's work, so it is not a scoring bug.

    Recognised **by the shape of the ref** rather than by `second_card`, which
    answers with the parent and so only knows a card whose parent is
    *declared*. Twelve are orphans -- `f1334b`, `f3529b` and ten more whose
    feat nobody has written -- and those went on being offered after the first
    fix, which is how the shape rule got measured: every ref in the `feat`
    table is either `f<digits>` or `f<digits><letters>`, and nothing that is
    really a feat carries a suffix.
    """
    import re

    from combat_engine.engine.dsl import REGISTRY

    from . import Character, build_of, meets

    second_block = re.compile(r"f\d+[a-z]+").fullmatch
    leg = build or build_of(cls)
    gates = feat_gates()
    who = Character(cls=cls, level=level, build=leg.name, race=race)
    held = list(taken)
    return [
        ref
        for ref in sorted(gates)
        if ref in REGISTRY
        and not REGISTRY[ref].todo
        # Superseded by a rules change: not a candidate for anybody.
        and not REGISTRY[ref].obsolete
        and not second_block(ref)
        and ref not in held
        and meets(gates[ref], who, held)
    ]


def feat_options(
    legal: list[str], cls: str, build: Build | None = None
) -> list[Choice]:
    """The feats this character could take, ranked.

    `legal` is handed in rather than worked out here: `feats_for` already knows
    which gates this character meets and re-deriving it would be the same query
    twice and a second place for the answer to be wrong.
    """
    from combat_engine.engine.dsl import REGISTRY

    from . import IMPLEMENTS, PRINTED, build_of

    leg = build or build_of(cls)
    armed = swings_a_weapon(cls, leg)
    unlocks = _prerequisite_counts()
    out: list[Choice] = []
    for ref in legal:
        declared = REGISTRY.get(ref)
        if declared is None:
            continue
        if _use_ratings() and _on_a_dump_stat(declared, leg):
            # Refused outright rather than scored down: a feat paying off only
            # through an ability this build dumped is not a weaker choice, it is
            # the wrong build's choice.
            continue
        opened = [
            PRINTED.get(w) or IMPLEMENTS.get(w)
            for w in (getattr(declared, "proficiency", ()) or ())
        ]
        weapons = [w for w in opened if w is not None and w.group != "implement"]
        score, terms = _priced(
            {
                "leans_on_build": float(_leaning(declared, leg, ref)),
                "opens_a_weapon": float(bool(weapons) and armed),
                "weapon_is_superior": float(
                    armed and any(w.category == "superior" for w in weapons)
                ),
                "implement_only_build": float(bool(weapons) and not armed),
                "grants_a_row": float(_granting(declared, ref)),
                "unlocks_other_feats": float(unlocks.get(ref, 0)),
                "carries_a_marker": float(bool(getattr(declared, "dropped", ()) or ())),
                "out_of_combat": float(getattr(declared, "out_of_combat", False)),
                **_rating_term(ref, cls),
            }
        )
        out.append(Choice(ref=ref, score=score, terms=terms))
    return _ranked(out)


def wield_options(
    candidates: list[Weapon], spent: set[str], known: list[str]
) -> list[Choice]:
    """Which of the weapons a character may carry it should actually hold.

    `outfit` used to bench every granted arm, and said why: "which of the
    weapons a character *may* carry it actually wields is a build choice, and
    nothing records one." This records one.

    `known` is the character's own rows, and it is what makes this safe. The
    naive rule -- swing whichever hits hardest -- puts a rogue's dagger away
    for a spiked chain and silently kills every light-blade Requirement the
    rogue's own cards are written against. `keeps_class_rows` counts those, so
    the rule has to beat them rather than ignore them.

    **`spent` is the refs a *feat* opened up, and nothing else.** A race trains
    a character in weapons through the same header field, so the list `outfit`
    used to build held both -- and priced a racial longsword as though a feat
    slot had been spent on it. That is not Camille's rule and it beat a
    ranger's own short swords with a weapon nobody chose.

    **This score answers "which weapon" and cannot answer "how many".** A
    requirement is sometimes about the count rather than the kind -- a
    two-blade ranger's rows say "must be wielding two melee weapons" and name
    no group, so no word here matches them. `outfit` holds the count fixed for
    exactly that reason, and the two mechanisms together cover both shapes
    of the sentence. Neither does the other's job.
    """
    out: list[Choice] = []
    for arm in candidates:
        score, terms = _priced(
            {
                "spent_a_feat": float(arm.ref in spent),
                "keeps_class_rows": float(_rows_needing(known, arm)),
                "damage_die": _average(arm.damage),
                "high_crit": float("high crit" in arm.properties),
                "versatile": float("versatile" in arm.properties),
                "reach_weapon": float("reach" in arm.properties),
            }
        )
        out.append(Choice(ref=arm.ref, score=score, terms=terms))
    return _ranked(out)


def _leaning(declared, leg: Build, ref: str) -> int:  # noqa: ANN001
    """`chargen._leans_on`, remembered. See `_LEANS` for why that matters."""
    from . import _leans_on

    key = (ref, leg.name)
    if key not in _LEANS:
        _LEANS[key] = _leans_on(declared, leg)
    return _LEANS[key]


def _granting(declared, ref: str) -> bool:  # noqa: ANN001
    """`_hands_over_a_row`, remembered. See `_GRANTS`."""
    if ref not in _GRANTS:
        _GRANTS[ref] = _hands_over_a_row(declared)
    return _GRANTS[ref]


def _hands_over_a_row(declared) -> bool:  # noqa: ANN001
    """Does this feat's whole benefit include handing over a card?

    Read off the body, the way `_leans_on` reads it for the ability: there is
    no header field that says so. `Power.grants` does not exist -- I looked --
    and the `fNNN` / `fNNNb` suffix is not reliable either, because the pair a
    feat forms is sometimes with a card that has a number of its own
    (`f959` grants `f960b`). What is always true is that the body calls
    `c.grant_row`.
    """
    import inspect

    try:
        return "c.grant_row(" in inspect.getsource(declared.body)
    except (OSError, TypeError):
        return False


def _rows_needing(known: list[str], arm: Weapon) -> int:
    """How many of this character's own rows name what this weapon is.

    Reads `requires_text` and `trigger`, which is where `audit.py`'s
    `_hand_it_the_weapon` reads the same sentence for 257 rows -- "you must be
    wielding a light blade" is a gate on gear whether it is printed as a
    Requirement or inside a trigger.
    """
    from combat_engine.engine.dsl import REGISTRY

    words = {arm.group, *arm.properties}
    words.discard("")
    count = 0
    for ref in known:
        declared = REGISTRY.get(ref)
        if declared is None:
            continue
        said = " ".join(
            (
                getattr(declared, "requires_text", "") or "",
                getattr(declared, "trigger", "") or "",
            )
        ).lower()
        if said and any(word in said for word in words):
            count += 1
    return count


def _average(damage: str) -> float:
    """The average of a printed damage expression -- `1d8` is 4.5, `2d4` is 5.

    **The count matters and reading only the faces inverts the answer.** A
    spiked chain is `2d4` and a longsword `1d8`; on faces alone the longsword
    scores twice as high and it is the weaker weapon. Caught by a fighter that
    took the chain feat and then held a racial longsword instead.
    """
    count, _, faces = (damage or "").partition("d")
    if not faces.isdigit():
        return 0.0
    dice = int(count) if count.isdigit() else 1
    return dice * (int(faces) + 1) / 2


def sample(
    options: list[Choice], rng: Random, *, top: int = 0, floor: float = FLOOR
) -> Choice | None:
    """One option, drawn with weight proportional to score. Never argmax.

    Scores are shifted so the worst option sits at `floor` rather than at zero
    or below -- a negative weight is not a probability, and a zero one makes an
    option unreachable, which is the thing this is written to avoid.

    `top` narrows the field first. See `FLOOR` for why that is necessary rather
    than tidy: on a pool of several hundred, the also-rans outweigh the good
    options by their number alone.
    """
    if not options:
        return None
    pool = _ranked(options)[: top or len(options)]
    worst = min(c.score for c in pool)
    weights = [c.score - worst + floor for c in pool]
    total = sum(weights)
    if total <= 0:
        return rng.choice(pool)
    cut = rng.random() * total
    for choice, weight in zip(pool, weights, strict=True):
        cut -= weight
        if cut <= 0:
            return choice
    return pool[-1]
